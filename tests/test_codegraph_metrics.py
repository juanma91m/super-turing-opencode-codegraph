from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "codegraph_metrics.py"
SPEC = importlib.util.spec_from_file_location("codegraph_metrics", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def assistant_message(
    *,
    tokens: int,
    tools: list[tuple[str, str, str]],
    model: str = "gpt-5.6",
) -> dict:
    return {
        "info": {
            "role": "assistant",
            "providerID": "openai",
            "modelID": model,
            "agent": "code-inspector",
            "tokens": {
                "total": tokens,
                "input": max(tokens - 10, 0),
                "output": min(tokens, 10),
                "reasoning": 0,
                "cache": {"read": 0, "write": 0},
            },
            "time": {"created": 1000, "completed": 1200},
        },
        "parts": [
            {
                "type": "tool",
                "tool": name,
                "state": {
                    "status": status,
                    "output": output,
                    "time": {"start": 1000, "end": 1100},
                },
            }
            for name, status, output in tools
        ],
    }


def exported_session(session_id: str, messages: list[dict], project: str = "higyrus") -> dict:
    return {
        "info": {
            "id": session_id,
            "directory": f"/workspace/{project}",
            "time": {"created": 1000, "updated": 5000},
        },
        "messages": messages,
    }


def record(
    pair_id: str,
    variant: str,
    tokens: int,
    manual_calls: int,
    outcome: str = "accepted",
    model: str = "openai/gpt-5.6",
) -> dict:
    codegraph_calls = 1 if variant == "with-codegraph" else 0
    return {
        "schema_version": 2,
        "captured_at": "2026-09-11T00:00:00+00:00",
        "experiment": "codegraph-ab",
        "pair_id": pair_id,
        "project": "higyrus",
        "variant": variant,
        "task_kind": "blast-radius",
        "task_id": pair_id,
        "policy_version": "policy-1",
        "scope": {"boundary_kind": "dedicated-task-session"},
        "outcome": outcome,
        "budget": {
            "applicable": variant == "with-codegraph",
            "calls_compliant": True,
            "output_compliant": True,
        },
        "metrics": {
            "session": {"project": "higyrus", "duration_ms": tokens * 2},
            "timing": {"assistant_wall_ms": tokens},
            "tokens": {"total": tokens},
            "models": {model: 1},
            "search": {
                "codegraph": {"calls": codegraph_calls, "output_bytes": 100},
                "manual": {"calls": manual_calls, "output_bytes": manual_calls * 100},
                "combined": {
                    "output_bytes": manual_calls * 100 + codegraph_calls * 100
                },
            },
        },
    }


class CodeGraphMetricsTest(unittest.TestCase):
    def test_compute_session_metrics_splits_graph_and_manual_search(self) -> None:
        exported = exported_session(
            "ses_test",
            [
                assistant_message(tokens=100, tools=[("grep", "completed", "abc")]),
                assistant_message(
                    tokens=200,
                    tools=[("mcp__codegraph__explore", "completed", "graph-output")],
                ),
                assistant_message(tokens=50, tools=[("read", "completed", "verify")]),
            ],
        )
        metrics = MODULE.compute_session_metrics(exported)
        self.assertEqual(metrics["tokens"]["total"], 350)
        self.assertEqual(metrics["search"]["codegraph"]["calls"], 1)
        self.assertEqual(metrics["search"]["codegraph"]["output_bytes"], 12)
        self.assertEqual(metrics["search"]["manual"]["calls"], 2)
        self.assertEqual(
            metrics["search"]["manual"]["before_first_codegraph"]["calls"], 1
        )
        self.assertEqual(
            metrics["search"]["manual"]["after_first_codegraph"]["calls"], 1
        )

    def test_variant_validation_rejects_mislabeled_sessions(self) -> None:
        exported = exported_session(
            "ses_test",
            [assistant_message(tokens=100, tools=[("codegraph_explore", "completed", "x")])],
        )
        metrics = MODULE.compute_session_metrics(exported)
        with self.assertRaises(ValueError):
            MODULE.validate_variant(metrics, "without-codegraph")

    def test_report_uses_only_accepted_compatible_pairs(self) -> None:
        records = [
            record("pair-1", "without-codegraph", 1000, 10),
            record("pair-1", "with-codegraph", 700, 4),
            record("pair-2", "without-codegraph", 2000, 20),
            record("pair-2", "with-codegraph", 1000, 5),
            record("pair-3", "without-codegraph", 500, 2),
            record("pair-3", "with-codegraph", 400, 1, outcome="partial"),
        ]
        report = MODULE.build_report(records)
        self.assertEqual(report["complete_accepted_pairs"], 2)
        self.assertEqual(report["aggregate"]["total_tokens"]["without_codegraph_median"], 1500)
        self.assertEqual(report["aggregate"]["total_tokens"]["with_codegraph_median"], 850)
        self.assertEqual(
            report["aggregate"]["total_tokens"]["paired_improvement_pct_median"],
            40,
        )
        self.assertAlmostEqual(
            report["quality"]["with-codegraph"]["acceptance_rate_pct"], 200 / 3
        )
        self.assertEqual(report["excluded_pairs"][0]["reason"], "resultado no aceptado")

    def test_unknown_tokens_output_and_latency_are_not_zero(self) -> None:
        message = assistant_message(tokens=100, tools=[("codegraph_explore", "completed", "x")])
        del message["info"]["tokens"]["total"]
        del message["parts"][0]["state"]["time"]
        del message["parts"][0]["state"]["output"]
        metrics = MODULE.compute_session_metrics(exported_session("s", [message]))
        self.assertIsNone(metrics["tokens"]["total"])
        self.assertEqual(metrics["token_coverage"]["total"]["missing"], 1)
        self.assertIsNone(metrics["search"]["codegraph"]["output_bytes"])
        self.assertIsNone(metrics["search"]["codegraph"]["wall_ms"])

    def test_missing_one_token_observation_invalidates_field_not_other_fields(self) -> None:
        first = assistant_message(tokens=100, tools=[])
        second = assistant_message(tokens=200, tools=[])
        del second["info"]["tokens"]["total"]
        metrics = MODULE.compute_session_metrics(exported_session("s", [first, second]))
        self.assertIsNone(metrics["tokens"]["total"])
        self.assertEqual(metrics["tokens"]["input"], 280)

    def test_overlap_does_not_double_count_active_time(self) -> None:
        self.assertEqual(MODULE.interval_union_ms([(0, 10), (5, 15), (20, 30)]), 25)

    def test_legacy_pair_excluded_and_unknown_metric_has_no_percentage(self) -> None:
        records = [record("p", v, 100, 1) for v in MODULE.VARIANTS]
        records[0]["schema_version"] = 1
        self.assertEqual(MODULE.build_report(records)["complete_accepted_pairs"], 0)
        records[0]["schema_version"] = 2
        records[0]["metrics"]["tokens"]["total"] = None
        report = MODULE.build_report(records)
        self.assertIsNone(report["aggregate"]["total_tokens"]["paired_improvement_pct_median"])
        self.assertEqual(report["aggregate"]["total_tokens"]["available_pairs"], 0)

    def test_pair_rejects_policy_model_scope_and_duplicate_mismatch(self) -> None:
        original = [record("p", v, 100, 1) for v in MODULE.VARIANTS]
        for field, value in (("policy_version", "policy-2"), ("task_id", "other")):
            records = copy.deepcopy(original)
            records[0][field] = value
            self.assertEqual(MODULE.build_report(records)["complete_accepted_pairs"], 0)
        records = copy.deepcopy(original)
        records[0]["metrics"]["models"]["other/model"] = 1
        records[1]["metrics"]["models"]["other/model"] = 1
        self.assertEqual(MODULE.build_report(records)["complete_accepted_pairs"], 0)
        self.assertEqual(MODULE.build_report(original + [original[0]])["complete_accepted_pairs"], 0)

    def test_pending_outcome_is_not_an_implicit_failure(self) -> None:
        report = MODULE.build_report([record("p", "with-codegraph", 1, 1, outcome="pending")])
        self.assertIsNone(report["quality"]["with-codegraph"]["acceptance_rate_pct"])
        self.assertEqual(report["quality"]["with-codegraph"]["evaluated_runs"], 0)


if __name__ == "__main__":
    unittest.main()
