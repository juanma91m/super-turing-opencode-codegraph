from __future__ import annotations

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
        "captured_at": "2026-09-11T00:00:00+00:00",
        "experiment": "codegraph-ab",
        "pair_id": pair_id,
        "project": "higyrus",
        "variant": variant,
        "task_kind": "blast-radius",
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


if __name__ == "__main__":
    unittest.main()
