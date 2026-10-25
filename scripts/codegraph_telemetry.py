"""On-demand telemetry adapter. Never selects prompts, tool inputs or raw outputs."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codegraph_metrics import compute_session_metrics, distribution, format_value, now_iso


@contextmanager
def read_database(path: Path):
    # No default connection: a typo must never create an empty database.
    path = path.expanduser().resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for table, required in {
            "session": {"id", "parent_id", "directory"},
            "message": {"id", "session_id", "time_created", "data"},
            "part": {"id", "message_id", "session_id", "time_created", "data"},
        }.items():
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise ValueError(f"Esquema de telemetría no compatible: {table}")
        yield db
    except sqlite3.Error as exc:
        raise RuntimeError(f"No se pudo consultar telemetría read-only: {exc}") from exc
    finally:
        db.close()


def parse_time(value: str) -> int:
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return int(date.timestamp() * 1000)


def session_catalog(db) -> dict[str, dict[str, Any]]:
    catalog = {row["id"]: dict(row) for row in db.execute("SELECT id,parent_id,directory FROM session")}
    return catalog


def root_of(sid: str, catalog: dict[str, dict[str, Any]]) -> str:
    seen = set()
    while sid in catalog and catalog[sid]["parent_id"] in catalog:
        if sid in seen:
            raise ValueError("Ciclo en relaciones parent_id; no se puede evitar doble conteo")
        seen.add(sid)
        sid = catalog[sid]["parent_id"]
    return sid


def descendants(sid: str, catalog: dict[str, dict[str, Any]]) -> set[str]:
    children = defaultdict(set)
    for child, data in catalog.items():
        children[data["parent_id"]].add(child)
    selected = {sid}
    pending = [sid]
    while pending:
        parent = pending.pop()
        for child in children[parent]:
            if child in selected:
                raise ValueError("Ciclo en relaciones de delegación")
            selected.add(child)
            pending.append(child)
    return selected


def load_events(db, since: int, until: int, session_ids: set[str] | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Project only numeric usage, IDs, tool names, timing and status in SQL."""
    messages = defaultdict(dict)
    session_filter = ""
    params: tuple = (since, until)
    if session_ids is not None:
        session_filter = " AND session_id IN (" + ",".join("?" for _ in session_ids) + ")"
        params += tuple(sorted(session_ids))
    rows = db.execute("""
        SELECT id,session_id,time_created,
          json_extract(data,'$.role') role,
          json_extract(data,'$.providerID') provider,
          json_extract(data,'$.modelID') model,
          json_extract(data,'$.variant') variant,
          json_extract(data,'$.agent') agent,
          json_extract(data,'$.time.created') started,
          json_extract(data,'$.time.completed') completed,
          json_extract(data,'$.tokens.total') total,
          json_extract(data,'$.tokens.input') input,
          json_extract(data,'$.tokens.output') output,
          json_extract(data,'$.tokens.reasoning') reasoning,
          json_extract(data,'$.tokens.cache.read') cache_read,
          json_extract(data,'$.tokens.cache.write') cache_write
        FROM message WHERE time_created>=? AND time_created<?
    """ + session_filter + " ORDER BY time_created,id", params)
    for row in rows:
        messages[row["session_id"]][row["id"]] = {
            "id": row["id"], "event_time": row["time_created"],
            "info": {
                "role": row["role"], "providerID": row["provider"], "modelID": row["model"],
                "variant": row["variant"], "agent": row["agent"],
                "time": {"created": row["started"], "completed": row["completed"]},
                "tokens": {**{key: row[key] for key in ("total", "input", "output", "reasoning")},
                           "cache": {"read": row["cache_read"], "write": row["cache_write"]}},
            }, "parts": [],
        }
    rows = db.execute("""
        SELECT id,message_id,session_id,time_created,
          json_extract(data,'$.tool') tool,
          json_extract(data,'$.state.status') status,
          length(CAST(json_extract(data,'$.state.output') AS BLOB)) output_bytes,
          json_extract(data,'$.state.time.start') started,
          json_extract(data,'$.state.time.end') completed
        FROM part WHERE time_created>=? AND time_created<?
          AND json_extract(data,'$.type')='tool'
    """ + session_filter + " ORDER BY time_created,id", params)
    for row in rows:
        message = messages[row["session_id"]].setdefault(row["message_id"], {
            "id": row["message_id"], "event_time": row["time_created"],
            "info": {}, "parts": [],
        })
        message["parts"].append({
            "id": row["id"], "type": "tool", "tool": row["tool"],
            "state": {"status": row["status"], "output_bytes": row["output_bytes"],
                      "time": {"start": row["started"], "end": row["completed"]}},
        })
    return messages


def aggregate_family(sids: set[str], events, primary: str | None = None):
    messages = [message for sid in sorted(sids) for message in events.get(sid, {}).values()]
    messages.sort(key=lambda message: (message["event_time"], message["id"]))
    metrics = compute_session_metrics({"info": {"id": primary}, "messages": messages})
    tool_names = metrics["tools"]["by_name"]
    metrics["delegation"] = {
        "linked_sessions_observed": len({sid for sid in sids if events.get(sid)}),
        "delegation_calls": sum(count for name, count in tool_names.items()
                                if name in ("task", "delegate", "delegate_isolated")),
        "link_source": "session.parent_id",
        "external_or_unlinked_work": None,
    }
    return metrics


def capture_metrics(args):
    for name in ("pair_id", "project", "task_kind", "policy_version"):
        if not str(getattr(args, name)).strip():
            raise ValueError(f"{name} no puede estar vacío")
    if args.corrections_required is not None and args.corrections_required < 0:
        raise ValueError("corrections-required no puede ser negativo")
    bounded = bool(args.from_message or args.to_message)
    if bounded and not (args.from_message and args.to_message):
        raise ValueError("Indicar ambos --from-message y --to-message")
    if bounded and args.dedicated_task:
        raise ValueError("Elegir rango de mensajes O --dedicated-task")
    if not bounded and not args.dedicated_task:
        raise ValueError("Delimitar la tarea con un rango de mensajes o --dedicated-task explícito")
    with read_database(args.database) as db:
        catalog = session_catalog(db)
        if args.session not in catalog:
            raise ValueError("Session ID no encontrado en la base indicada")
        family = descendants(args.session, catalog)
        since, until = 0, 2**63 - 1
        selected_ids = None
        if bounded:
            root_messages = list(db.execute("""
                SELECT id,time_created,json_extract(data,'$.time.completed') completed
                FROM message WHERE session_id=? ORDER BY time_created,id
            """, (args.session,)))
            indices = {row["id"]: index for index, row in enumerate(root_messages)}
            if args.from_message not in indices or args.to_message not in indices:
                raise ValueError("Los límites deben existir en la sesión principal")
            left, right = indices[args.from_message], indices[args.to_message]
            if left > right:
                raise ValueError("Rango de mensajes invertido")
            selected_ids = {row["id"] for row in root_messages[left:right+1]}
            since = root_messages[left]["time_created"]
            last = root_messages[right]
            until = max(last["time_created"], last["completed"] or last["time_created"]) + 1
        events = load_events(db, since, until, family)
        if selected_ids is not None:
            events[args.session] = {key: value for key, value in events.get(args.session, {}).items() if key in selected_ids}
        metrics = aggregate_family(family, events, args.session)
        if not any(events.get(sid) for sid in family):
            raise ValueError("El alcance seleccionado no contiene eventos")
        return metrics, {
            "boundary_kind": "message-range" if bounded else "dedicated-task-session",
            "from_message": args.from_message, "to_message": args.to_message,
            "linked_sessions": sorted(sid for sid in family if events.get(sid)),
            "descendant_attribution": "parent_id; rango temporal para tareas delimitadas",
            "unlinked_work_complete": None,
        }


def history_report(args):
    since, until = parse_time(args.since), parse_time(args.until)
    if since >= until:
        raise ValueError("--since debe ser anterior a --until (exclusivo)")
    with read_database(args.database) as db:
        catalog = session_catalog(db)
        events = load_events(db, since, until)
        families = defaultdict(set)
        for sid in events:
            if sid in catalog:
                families[root_of(sid, catalog)].add(sid)
        groups = defaultdict(list)
        roots_selected = 0
        for root, members in sorted(families.items()):
            directory = catalog[root]["directory"] or ""
            if args.project_root and Path(directory).resolve() != args.project_root.expanduser().resolve():
                continue
            metrics = aggregate_family(members, events, root)
            models = sorted(metrics["models"])
            if args.model and models != [args.model]:
                continue
            roots_selected += 1
            project_key = hashlib.sha256(directory.encode()).hexdigest()[:12]
            project = Path(directory).name or "unknown"
            cohort = "with-codegraph" if metrics["search"]["codegraph"]["calls"] else "without-codegraph"
            groups[(project, project_key, tuple(models), cohort)].append(metrics)
        rows = []
        for (project, project_key, models, cohort), units in sorted(groups.items()):
            fields = {
                **{f"tokens_{name}": [unit["tokens"][name] for unit in units]
                   for name in ("total", "input", "cache_read", "cache_write", "output", "reasoning")},
                "assistant_work_ms": [unit["timing"]["assistant_wall_ms"] for unit in units],
                "assistant_active_union_ms": [unit["timing"]["assistant_active_union_ms"] for unit in units],
                "codegraph_calls": [unit["search"]["codegraph"]["calls"] for unit in units],
                "codegraph_output_bytes": [unit["search"]["codegraph"]["output_bytes"] for unit in units],
                "codegraph_work_ms": [unit["search"]["codegraph"]["wall_ms"] for unit in units],
                "codegraph_latency_ms": [unit["search"]["codegraph"]["latency_ms"]["median"] for unit in units],
                "manual_calls": [unit["search"]["manual"]["calls"] for unit in units],
                "manual_output_bytes": [unit["search"]["manual"]["output_bytes"] for unit in units],
                "search_output_bytes": [unit["search"]["combined"]["output_bytes"] for unit in units],
                "linked_sessions": [unit["delegation"]["linked_sessions_observed"] for unit in units],
                "delegation_calls": [unit["delegation"]["delegation_calls"] for unit in units],
            }
            rows.append({"project": project, "project_key": project_key, "models": list(models),
                         "cohort": cohort, "families": len(units),
                         "metrics": {name: distribution(values) for name, values in fields.items()},
                         "tool_statuses": dict(sum((Counter(unit["search"]["codegraph"]["by_status"]) for unit in units), Counter())),
                         "task_kind": None, "policy_version": None,
                         "acceptance_rate": None, "verified_utility": None})
    return {
        "schema_version": 2, "kind": "observational-history", "generated_at": now_iso(),
        "window": {"since_inclusive": args.since, "until_exclusive": args.until},
        "families": roots_selected, "groups": rows,
        "methodology": {
            "unit": "non-overlapping root session family active in window, NOT task",
            "delegation": "parent_id only; each observed session counted once; external/unlinked work unknown",
            "timing": "assistant_work sums durations; active_union merges overlap and excludes idle gaps; neither is elapsed task time",
            "tokens": "provider fields only; missing observations are null, not zero; cache/reasoning are not added to reported total",
            "output": "stored tool output bytes computed in SQL, not model-visible tokens",
            "snapshot": "event creation in window, latest stored state; not a reconstruction of past in-flight state",
            "quality": "not inferred; completed tool status does not prove semantic success",
            "causality": "no paired tasks; no causal savings percentage is calculated",
            "privacy": "no prompts, tool inputs, raw outputs, session IDs or full project paths persisted",
        },
    }


def history_markdown(report):
    lines = ["# CodeGraph — telemetría histórica observacional", "",
             f"Ventana UTC: {report['window']['since_inclusive']} → {report['window']['until_exclusive']} (fin exclusivo)",
             f"Familias de sesiones: {report['families']}. No equivalen a tareas aceptadas.", "",
             "No se calcula ahorro causal. Datos ausentes: n/a (no cero).", "",
             "| Proyecto | Modelo | Cohorte | Familias | Tokens totales mediana (n) | CG llamadas mediana | CG bytes mediana | Manual mediana |",
             "|---|---|---|---:|---:|---:|---:|---:|"]
    for group in report["groups"]:
        m = group["metrics"]
        lines.append(f"| {group['project']} ({group['project_key']}) | {', '.join(group['models']) or 'n/a'} | "
                     f"{group['cohort']} | {group['families']} | {format_value(m['tokens_total']['median'])} "
                     f"({m['tokens_total']['available']}) | {format_value(m['codegraph_calls']['median'])} | "
                     f"{format_value(m['codegraph_output_bytes']['median'])} | {format_value(m['manual_calls']['median'])} |")
    lines += ["", "## Desglose por cohorte (medianas; n = familias con dato)", ""]
    for group in report["groups"]:
        lines += [f"### {group['project']} / {', '.join(group['models']) or 'n/a'} / {group['cohort']}", "",
                  "| Métrica | Mediana | P75 | P90 | n | Ausentes |", "|---|---:|---:|---:|---:|---:|"]
        for name, values in group["metrics"].items():
            lines.append(f"| {name} | {format_value(values['median'])} | {format_value(values['p75'])} | "
                         f"{format_value(values['p90'])} | {values['available']} | {values['missing']} |")
    lines += ["", "Calidad, correcciones, política histórica y tipo de tarea: no disponibles sin evaluación explícita.",
              "Trabajo delegado no vinculado: no disponible. Estado completed no garantiza utilidad.", ""]
    return "\n".join(lines)
