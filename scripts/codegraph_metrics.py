#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


VARIANTS = ("with-codegraph", "without-codegraph")
OUTCOMES = ("accepted", "partial", "reworked", "incorrect", "pending")
UTILITIES = ("yes", "partial", "no", "not-evaluated", "not-applicable")
MANUAL_SEARCH_TOOLS = {"glob", "grep", "read"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(microsecond=0).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("El identificador no puede quedar vacío")
    return slug


def run_export(session_id: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        with temp_path.open("w", encoding="utf-8") as target:
            proc = subprocess.run(
                ["opencode", "export", "--sanitize", session_id],
                stdout=target,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"No se pudo exportar la sesión {session_id}: {proc.stderr.strip()}"
            )
        try:
            return json.loads(temp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"La exportación sanitizada de {session_id} no devolvió JSON válido"
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def serialized_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return len(text.encode("utf-8"))


def canonical_tool_name(value: Any) -> str:
    name = str(value or "unknown").strip().lower()
    for separator in ("::", "__", ".", "/"):
        if separator in name:
            name = name.split(separator)[-1]
    return name


def is_codegraph_tool(value: Any) -> bool:
    return "codegraph" in str(value or "").lower()


def tool_duration_ms(state: dict[str, Any]) -> int | None:
    timing = state.get("time") or {}
    start = timing.get("start", timing.get("created"))
    end = timing.get("end", timing.get("completed"))
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return end - start
    return None


def observed_sum(values: list[int | float | None]) -> int | float | None:
    """Empty populations are zero; incomplete observations are not zero."""
    return None if any(value is None for value in values) else sum(values)


def model_label(meta: dict[str, Any]) -> str | None:
    provider = meta.get("providerID") or ((meta.get("model") or {}).get("providerID"))
    model = meta.get("modelID") or ((meta.get("model") or {}).get("modelID"))
    variant = meta.get("variant") or ((meta.get("model") or {}).get("variant"))
    label = "/".join(filter(None, [provider, model]))
    if variant and label:
        label = f"{label}#{variant}"
    return label or None


def summarize_tools(events: list[dict[str, Any]]) -> dict[str, Any]:
    codegraph_events = [event for event in events if event["category"] == "codegraph"]
    manual_events = [event for event in events if event["category"] == "manual"]
    first_codegraph = codegraph_events[0]["position"] if codegraph_events else None
    before = [
        event
        for event in manual_events
        if first_codegraph is not None and event["position"] < first_codegraph
    ]
    after = [
        event
        for event in manual_events
        if first_codegraph is not None and event["position"] > first_codegraph
    ]

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = Counter(item["status"] for item in items)
        names = Counter(item["name"] for item in items)
        return {
            "calls": len(items),
            "output_bytes": observed_sum([item["output_bytes"] for item in items]),
            "wall_ms": observed_sum([item["duration_ms"] for item in items]),
            "latency_ms": distribution([item["duration_ms"] for item in items]),
            "by_name": dict(sorted(names.items())),
            "by_status": dict(sorted(statuses.items())),
        }

    codegraph = aggregate(codegraph_events)
    manual = aggregate(manual_events)
    manual["before_first_codegraph"] = aggregate(before)
    manual["after_first_codegraph"] = aggregate(after)
    return {
        "codegraph": codegraph,
        "manual": manual,
        "combined": {
            "calls": codegraph["calls"] + manual["calls"],
            "output_bytes": observed_sum([codegraph["output_bytes"], manual["output_bytes"]]),
        },
        "first_codegraph_tool_position": first_codegraph,
    }


def compute_session_metrics(exported: dict[str, Any]) -> dict[str, Any]:
    info = exported.get("info") or {}
    messages = exported.get("messages") or []
    tokens = {
        "total": 0,
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
    }
    token_values: dict[str, list[int | None]] = {name: [] for name in tokens}
    model_counts: Counter[str] = Counter()
    agent_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    events: list[dict[str, Any]] = []
    assistant_times: list[int | None] = []
    assistant_intervals: list[tuple[int, int]] = []
    tool_position = 0

    for message in messages:
        meta = message.get("info") or {}
        if meta.get("role") == "assistant":
            label = model_label(meta)
            if label:
                model_counts[label] += 1
            agent = meta.get("agent") or meta.get("mode")
            if agent:
                agent_counts[str(agent)] += 1
            token_meta = meta.get("tokens") or {}
            cache = token_meta.get("cache") or {}
            for name in token_values:
                value = cache.get(name.removeprefix("cache_")) if name.startswith("cache_") else token_meta.get(name)
                token_values[name].append(value if isinstance(value, (int, float)) and value >= 0 else None)
            timing = meta.get("time") or {}
            created = timing.get("created")
            completed = timing.get("completed")
            if isinstance(created, int) and isinstance(completed, int) and completed >= created:
                assistant_times.append(completed - created)
                assistant_intervals.append((created, completed))
            else:
                assistant_times.append(None)

        for part in message.get("parts") or []:
            if part.get("type") != "tool":
                continue
            tool_position += 1
            raw_name = str(part.get("tool") or "unknown")
            name = canonical_tool_name(raw_name)
            tool_counts[raw_name] += 1
            state = part.get("state") or {}
            category = "other"
            if is_codegraph_tool(raw_name):
                category = "codegraph"
            elif name in MANUAL_SEARCH_TOOLS:
                category = "manual"
            events.append(
                {
                    "position": tool_position,
                    "name": name,
                    "category": category,
                    "status": str(state.get("status") or "unknown"),
                    "output_bytes": (
                        state["output_bytes"] if "output_bytes" in state else
                        serialized_size(state["output"]) if state.get("output") is not None else None
                    ),
                    "duration_ms": tool_duration_ms(state),
                }
            )

    for name, values in token_values.items():
        tokens[name] = observed_sum(values) if values else None
    session_time = info.get("time") or {}
    created = session_time.get("created")
    updated = session_time.get("updated")
    duration_ms = None
    if isinstance(created, int) and isinstance(updated, int) and updated >= created:
        duration_ms = updated - created

    directory = info.get("directory")
    project_name = None
    if (
        isinstance(directory, str)
        and directory
        and not directory.startswith("[redacted:")
    ):
        project_name = Path(directory).name
    return {
        "session": {
            "id": info.get("id"),
            "project": project_name,
            "created_at": ms_to_iso(created) if isinstance(created, int) else None,
            "updated_at": ms_to_iso(updated) if isinstance(updated, int) else None,
            "duration_ms": duration_ms,
        },
        "tokens": tokens,
        "models": dict(sorted(model_counts.items())),
        "agents": dict(sorted(agent_counts.items())),
        "token_coverage": {
            name: {"observations": len(values), "missing": sum(value is None for value in values)}
            for name, values in token_values.items()
        },
        "timing": {
            "assistant_wall_ms": observed_sum(assistant_times) if assistant_times else None,
            "assistant_active_union_ms": (
                interval_union_ms(assistant_intervals)
                if assistant_times and all(value is not None for value in assistant_times) else None
            ),
        },
        "tools": {
            "count": sum(tool_counts.values()),
            "by_name": dict(sorted(tool_counts.items())),
        },
        "search": summarize_tools(events),
    }


def interval_union_ms(intervals: list[tuple[int, int]]) -> int:
    total = 0
    start = end = None
    for left, right in sorted(intervals):
        if start is None:
            start, end = left, right
        elif left > end:
            total += end - start
            start, end = left, right
        else:
            end = max(end, right)
    return total + (end - start if start is not None else 0)


def validate_variant(metrics: dict[str, Any], variant: str) -> None:
    calls = metrics["search"]["codegraph"]["calls"]
    if variant == "with-codegraph" and calls == 0:
        raise ValueError("La variante with-codegraph no contiene llamadas CodeGraph")
    if variant == "without-codegraph" and calls != 0:
        raise ValueError("La variante without-codegraph contiene llamadas CodeGraph")


def load_marker(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "addon_version": data.get("version"),
        "codegraph_version": data.get("codegraphVersion"),
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.chmod(temp_path, 0o600)
    temp_path.replace(path)


def capture_record(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    from codegraph_telemetry import capture_metrics

    metrics, scope = capture_metrics(args)
    validate_variant(metrics, args.variant)
    session_id = metrics["session"].get("id")
    if session_id and session_id != args.session:
        raise ValueError(
            f"La captura devolvió otra sesión: esperada {args.session}, recibida {session_id}"
        )
    recommended_max_calls = 1 if "review" in args.task_kind.lower() else 3
    codegraph = metrics["search"]["codegraph"]
    record = {
        "schema_version": 2,
        "captured_at": now_iso(),
        "experiment": "codegraph-ab",
        "pair_id": args.pair_id,
        "project": args.project,
        "variant": args.variant,
        "task_kind": args.task_kind,
        "task_id": args.task_id or args.pair_id,
        "policy_version": args.policy_version,
        "scope": scope,
        "outcome": args.outcome,
        "evaluation": {
            "utility": args.utility,
            "corrections_required": args.corrections_required,
            "source": "explicit-operator-input",
        },
        "runtime": load_marker(args.marker),
        "runtime_provenance": "installation-at-capture; not historical session runtime",
        "budget": {
            "applicable": args.variant == "with-codegraph",
            "recommended_max_calls": recommended_max_calls,
            "recommended_max_output_bytes": 10 * 1024,
            "calls_compliant": (
                codegraph["calls"] <= recommended_max_calls
                if args.variant == "with-codegraph"
                else None
            ),
            "output_compliant": (
                codegraph["output_bytes"] <= 10 * 1024
                if args.variant == "with-codegraph" and codegraph["output_bytes"] is not None
                else None
            ),
        },
        "metrics": metrics,
    }
    identity = json.dumps([args.pair_id, args.variant, args.session, args.task_id or args.pair_id,
                           args.from_message, args.to_message], ensure_ascii=False)
    filename = "--".join([safe_slug(args.pair_id), args.variant,
                          hashlib.sha256(identity.encode()).hexdigest()[:20]]) + ".json"
    output = args.state_dir / "runs" / filename
    atomic_write_json(output, record)
    return record, output


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def distribution(values: list[int | float | None]) -> dict[str, Any]:
    known = [value for value in values if value is not None]
    return {
        "observations": len(values), "available": len(known),
        "missing": len(values) - len(known),
        "sum": observed_sum(values) if values else None,
        "mean": sum(known) / len(known) if known else None,
        "median": median(known) if known else None,
        "p75": percentile(known, .75), "p90": percentile(known, .90),
    }


def nested_number(record: dict[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = record
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return float(value) if isinstance(value, (int, float)) else None


def improvement_percent(with_value: float | None, without_value: float | None) -> float | None:
    if with_value is None or without_value is None or without_value == 0:
        return None
    return (without_value - with_value) / without_value * 100


def latest_by_variant(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: item.get("captured_at") or ""):
        selected[record["variant"]] = record
    return selected


def compatible_pair(with_record: dict[str, Any], without_record: dict[str, Any]) -> str | None:
    if with_record.get("task_kind") != without_record.get("task_kind"):
        return "task_kind distinto"
    with_metrics = with_record["metrics"]
    without_metrics = without_record["metrics"]
    if set(with_metrics.get("models") or {}) != set(without_metrics.get("models") or {}):
        return "modelo distinto"
    if with_record.get("project") != without_record.get("project"):
        return "proyecto distinto"
    if not with_metrics.get("models") or not without_metrics.get("models"):
        return "modelo no disponible"
    if len(with_metrics["models"]) != 1:
        return "múltiples modelos: no aislar efecto CodeGraph"
    if with_record.get("schema_version", 1) < 2 or without_record.get("schema_version", 1) < 2:
        return "registro legacy sin alcance de tarea/política verificable"
    for field in ("task_id", "policy_version"):
        if not with_record.get(field) or not without_record.get(field):
            return f"{field} no disponible"
        if with_record[field] != without_record[field]:
            return f"{field} distinto"
    if (with_record.get("scope") or {}).get("boundary_kind") not in ("message-range", "dedicated-task-session"):
        return "alcance de tarea no disponible"
    if with_record["scope"].get("boundary_kind") != (without_record.get("scope") or {}).get("boundary_kind"):
        return "alcances distintos"
    return None


REPORT_METRICS = {
    "total_tokens": ("metrics", "tokens", "total"),
    **{f"tokens_{name}": ("metrics", "tokens", name) for name in (
        "input", "cache_read", "cache_write", "output", "reasoning"
    )},
    "assistant_wall_ms": ("metrics", "timing", "assistant_wall_ms"),
    "assistant_active_union_ms": ("metrics", "timing", "assistant_active_union_ms"),
    "codegraph_latency_ms": ("metrics", "search", "codegraph", "latency_ms", "median"),
    "manual_calls": ("metrics", "search", "manual", "calls"),
    "manual_output_bytes": ("metrics", "search", "manual", "output_bytes"),
    "search_output_bytes": ("metrics", "search", "combined", "output_bytes"),
}


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    outcomes: dict[str, Counter[str]] = {variant: Counter() for variant in VARIANTS}
    utilities: dict[str, Counter[str]] = {variant: Counter() for variant in VARIANTS}
    budgets: dict[str, list[bool]] = {variant: [] for variant in VARIANTS}
    for record in records:
        grouped.setdefault(record["pair_id"], []).append(record)
        outcomes[record["variant"]][record.get("outcome") or "pending"] += 1
        utilities[record["variant"]][(record.get("evaluation") or {}).get("utility") or "not-evaluated"] += 1
        budget = record.get("budget") or {}
        if record["variant"] == "with-codegraph" and budget.get("applicable", True) and all(
            budget.get(field) is not None for field in ("calls_compliant", "output_compliant")
        ):
            budgets[record["variant"]].append(
                bool(budget.get("calls_compliant"))
                and bool(budget.get("output_compliant"))
            )

    complete_pairs: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for pair_id, pair_records in sorted(grouped.items()):
        if any(sum(r["variant"] == variant for r in pair_records) > 1 for variant in VARIANTS):
            excluded.append({"pair_id": pair_id, "reason": "más de una corrida por variante: usar pair-id único por repetición"})
            continue
        selected = latest_by_variant(pair_records)
        if not all(variant in selected for variant in VARIANTS):
            excluded.append({"pair_id": pair_id, "reason": "falta una variante"})
            continue
        with_record = selected["with-codegraph"]
        without_record = selected["without-codegraph"]
        if with_record.get("outcome") != "accepted" or without_record.get("outcome") != "accepted":
            excluded.append({"pair_id": pair_id, "reason": "resultado no aceptado"})
            continue
        incompatibility = compatible_pair(with_record, without_record)
        if incompatibility:
            excluded.append({"pair_id": pair_id, "reason": incompatibility})
            continue
        deltas: dict[str, float | None] = {}
        values: dict[str, dict[str, float]] = {}
        for name, path in REPORT_METRICS.items():
            with_value = nested_number(with_record, path)
            without_value = nested_number(without_record, path)
            values[name] = {
                "with_codegraph": with_value,
                "without_codegraph": without_value,
            }
            deltas[name] = improvement_percent(with_value, without_value)
        complete_pairs.append({
            "pair_id": pair_id, "values": values, "improvement_pct": deltas,
            "dimensions": {
                "project": with_record["project"], "model": next(iter(with_record["metrics"]["models"])),
                "task_kind": with_record["task_kind"], "policy_version": with_record["policy_version"],
            },
        })

    aggregate = summarize_pairs(complete_pairs)
    strata: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for pair in complete_pairs:
        key = tuple(pair["dimensions"][name] for name in ("project", "model", "task_kind", "policy_version"))
        strata.setdefault(key, []).append(pair)

    quality: dict[str, Any] = {}
    for variant in VARIANTS:
        counts = outcomes[variant]
        total = sum(counts.values())
        evaluated = total - counts["pending"]
        corrections = [(record.get("evaluation") or {}).get("corrections_required")
                       for record in records if record["variant"] == variant]
        quality[variant] = {
            "runs": total,
            "evaluated_runs": evaluated,
            "by_outcome": dict(sorted(counts.items())),
            "utility": dict(sorted(utilities[variant].items())),
            "corrections_required": distribution(corrections),
            "acceptance_rate_pct": (counts["accepted"] / evaluated * 100) if evaluated else None,
            "budget_compliance_rate_pct": (
                sum(budgets[variant]) / len(budgets[variant]) * 100
                if budgets[variant] else None
            ),
        }

    return {
        "schema_version": 2,
        "experiment": "codegraph-ab",
        "generated_at": now_iso(),
        "runs_total": len(records),
        "complete_accepted_pairs": len(complete_pairs),
        "quality": quality,
        "aggregate": aggregate,
        "strata": [{"dimensions": pairs[0]["dimensions"], "pairs": len(pairs), "aggregate": summarize_pairs(pairs)}
                   for _, pairs in sorted(strata.items())],
        "pairs": complete_pairs,
        "excluded_pairs": excluded,
    }


def summarize_pairs(complete_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    for name in REPORT_METRICS:
        available_pairs = [pair for pair in complete_pairs if all(
            pair["values"][name][variant] is not None for variant in ("with_codegraph", "without_codegraph")
        )]
        with_values = [pair["values"][name]["with_codegraph"] for pair in available_pairs]
        without_values = [pair["values"][name]["without_codegraph"] for pair in available_pairs]
        paired_deltas = [
            pair["improvement_pct"][name]
            for pair in complete_pairs
            if pair["improvement_pct"][name] is not None
        ]
        aggregate[name] = {
            "available_pairs": len(available_pairs),
            "missing_pairs": len(complete_pairs) - len(available_pairs),
            "with_codegraph_median": median(with_values) if with_values else None,
            "with_codegraph_p75": percentile(with_values, 0.75),
            "without_codegraph_median": median(without_values) if without_values else None,
            "without_codegraph_p75": percentile(without_values, 0.75),
            "paired_improvement_pct_median": median(paired_deltas) if paired_deltas else None,
        }

    return aggregate


def load_records(state_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((state_dir / "runs").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"No se pudo leer {path}: {exc}") from exc
        if record.get("experiment") == "codegraph-ab":
            records.append(record)
    return records


def format_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Benchmark A/B de CodeGraph",
        "",
        f"- Corridas: {report['runs_total']}",
        f"- Pares aceptados y comparables: {report['complete_accepted_pairs']}",
        f"- Pares excluidos: {len(report['excluded_pairs'])}",
        "",
        "## Resultado agregado",
        "",
        "Un porcentaje positivo indica mejora con CodeGraph; uno negativo indica regresión.",
        "",
        "Tokens incluyen caché y contexto repetido; no equivalen a costo facturado. n/a no significa cero.",
        "",
        "| Métrica | Sin CodeGraph (mediana) | Con CodeGraph (mediana) | Mejora pareada (mediana) | Pares con dato |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "total_tokens": "Tokens totales",
        **{f"tokens_{name}": f"Tokens {name}" for name in ("input", "cache_read", "cache_write", "output", "reasoning")},
        "assistant_wall_ms": "Tiempo de asistente (ms)",
        "assistant_active_union_ms": "Tiempo activo sin solapamientos (ms)",
        "codegraph_latency_ms": "Latencia CodeGraph por llamada (ms)",
        "manual_calls": "Llamadas manuales",
        "manual_output_bytes": "Output manual (bytes)",
        "search_output_bytes": "Output total de búsqueda (bytes)",
    }
    for name, values in report["aggregate"].items():
        lines.append(
            f"| {labels[name]} | {format_value(values['without_codegraph_median'])} | "
            f"{format_value(values['with_codegraph_median'])} | "
            f"{format_value(values['paired_improvement_pct_median'], '%')} | {values['available_pairs']} |"
        )

    lines.extend(
        [
            "",
            "## Calidad y presupuesto",
            "",
            "| Variante | Corridas | Aceptación | Cumplimiento de presupuesto |",
            "|---|---:|---:|---:|",
        ]
    )
    for variant in VARIANTS:
        values = report["quality"][variant]
        lines.append(
            f"| {variant} | {values['runs']} | "
            f"{format_value(values['acceptance_rate_pct'], '%')} | "
            f"{format_value(values['budget_compliance_rate_pct'], '%')} |"
        )
    lines.append("")
    for variant in VARIANTS:
        values = report["quality"][variant]
        lines.append(f"- {variant}: evaluadas {values['evaluated_runs']}/{values['runs']}; "
                     f"utilidad explícita {json.dumps(values['utility'], ensure_ascii=False)}; "
                     f"correcciones mediana {format_value(values['corrections_required']['median'])}.")
    if report.get("strata"):
        lines.extend(["", "## Resultados estratificados", ""])
        for group in report["strata"]:
            dims = group["dimensions"]
            value = group["aggregate"]["total_tokens"]
            lines.append(f"- {dims['project']} / {dims['model']} / {dims['task_kind']} / "
                         f"{dims['policy_version']}: {group['pairs']} pares, mejora tokens "
                         f"{format_value(value['paired_improvement_pct_median'], '%')}.")
    if report["excluded_pairs"]:
        lines.extend(["", "## Pares excluidos", ""])
        for item in report["excluded_pairs"]:
            lines.append(f"- `{item['pair_id']}`: {item['reason']}")
    lines.append("")
    return "\n".join(lines)


def command_capture(args: argparse.Namespace) -> int:
    record, output = capture_record(args)
    print(
        json.dumps(
            {
                "status": "ok",
                "file": str(output),
                "pair_id": record["pair_id"],
                "variant": record["variant"],
                "outcome": record["outcome"],
                "tokens_total": record["metrics"]["tokens"]["total"],
                "codegraph_calls": record["metrics"]["search"]["codegraph"]["calls"],
                "codegraph_output_bytes": record["metrics"]["search"]["codegraph"]["output_bytes"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def command_report(args: argparse.Namespace) -> int:
    report = build_report(load_records(args.state_dir))
    content = (
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.json
        else report_markdown(report)
    )
    if args.output:
        atomic_write_json(args.output, report) if args.json else write_private_text(args.output, content)
    print(content, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_state = Path(
        os.environ.get(
            "OPENCODE_CODEGRAPH_METRICS_DIR",
            "~/.local/state/super-turing-opencode-codegraph/benchmarks",
        )
    ).expanduser()
    default_marker = Path("~/.config/opencode/.opencode-codegraph-addon.json").expanduser()
    parser = argparse.ArgumentParser(
        description="Captura y compara métricas A/B sanitizadas de CodeGraph"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="Captura una tarea explícita y sus sesiones hijas verificables")
    capture.add_argument("--session", required=True)
    capture.add_argument("--variant", required=True, choices=VARIANTS)
    capture.add_argument("--pair-id", required=True)
    capture.add_argument("--project", required=True)
    capture.add_argument("--task-kind", required=True)
    capture.add_argument("--task-id", help="Default: pair-id")
    capture.add_argument("--policy-version", required=True, help="Etiqueta explícita de la política usada; no se infiere del runtime actual")
    capture.add_argument("--dedicated-task", action="store_true", help="Confirmar que la sesión completa corresponde a una tarea")
    capture.add_argument("--from-message", help="ID inicial inclusivo en la sesión principal")
    capture.add_argument("--to-message", help="ID final inclusivo en la sesión principal")
    capture.add_argument("--database", type=Path, default=Path("~/.local/share/opencode/opencode.db").expanduser())
    capture.add_argument("--utility", choices=UTILITIES, default="not-evaluated")
    capture.add_argument("--corrections-required", type=int)
    capture.add_argument("--outcome", required=True, choices=OUTCOMES)
    capture.add_argument("--state-dir", type=Path, default=default_state)
    capture.add_argument("--marker", type=Path, default=default_marker)
    capture.set_defaults(handler=command_capture)

    report = sub.add_parser("report", help="Genera el reporte agregado por pares")
    report.add_argument("--state-dir", type=Path, default=default_state)
    report.add_argument("--json", action="store_true")
    report.add_argument("--output", type=Path)
    report.set_defaults(handler=command_report)
    history = sub.add_parser("history", help="Reporte histórico observacional desde SQLite read-only; no requiere capturas")
    history.add_argument("--database", type=Path, default=Path("~/.local/share/opencode/opencode.db").expanduser())
    history.add_argument("--since", required=True, help="ISO-8601 UTC inclusivo")
    history.add_argument("--until", required=True, help="ISO-8601 UTC exclusivo")
    history.add_argument("--project-root", type=Path)
    history.add_argument("--model", help="Etiqueta exacta provider/model#variant; las familias mixtas no se recortan")
    history.add_argument("--json", action="store_true")
    history.add_argument("--output", type=Path)
    history.set_defaults(handler=command_history)
    return parser


def command_history(args: argparse.Namespace) -> int:
    from codegraph_telemetry import history_report, history_markdown

    if args.output and args.output.expanduser().resolve() == args.database.expanduser().resolve():
        raise ValueError("El reporte no puede sobrescribir la base de telemetría")
    report = history_report(args)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.json else history_markdown(report)
    if args.output:
        atomic_write_json(args.output, report) if args.json else write_private_text(args.output, content)
    print(content, end="")
    return 0


def write_private_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp = Path(handle.name)
    temp.replace(path)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
