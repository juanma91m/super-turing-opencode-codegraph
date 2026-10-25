from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


REPO = Path(__file__).parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import codegraph_metrics as metrics
import codegraph_telemetry as telemetry


class TelemetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "telemetry.db"
        self.db = sqlite3.connect(self.path)
        self.db.executescript("""
            CREATE TABLE session(id TEXT PRIMARY KEY,parent_id TEXT,directory TEXT);
            CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,time_created INTEGER,data TEXT);
            CREATE TABLE part(id TEXT PRIMARY KEY,message_id TEXT,session_id TEXT,time_created INTEGER,data TEXT);
        """)
        self.db.executemany("INSERT INTO session VALUES(?,?,?)", [
            ("root", None, "/private/work/repo"),
            ("child", "root", "/private/work/repo"),
            ("grand", "child", "/private/work/elsewhere"),
            ("other", None, "/private/work/repo"),
        ])
        for sid, started in (("root", 1000), ("child", 1100), ("grand", 1200), ("other", 1400)):
            self.add_message(sid, sid + "-msg", started)
        self.add_tool("child", "child-msg", 1101, "codegraph_codegraph_explore")
        self.add_tool("root", "root-msg", 1001, "delegate")
        self.add_tool("grand", "grand-msg", 1201, "read")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add_message(self, sid, mid, time, model="model", missing=False):
        token_meta = {"input": 80, "output": 10, "cache": {"read": 10, "write": 0}, "reasoning": 0}
        if not missing:
            token_meta["total"] = 100
        self.db.execute("INSERT INTO message VALUES(?,?,?,?)", (mid, sid, time, json.dumps({
            "role": "assistant", "providerID": "provider", "modelID": model,
            "tokens": token_meta, "time": {"created": time, "completed": time + 1000},
            "text": "PRIVATE_PROMPT_SENTINEL",
        })))

    def add_tool(self, sid, mid, time, name):
        self.db.execute("INSERT INTO part VALUES(?,?,?,?,?)", (mid + "-tool", mid, sid, time, json.dumps({
            "type": "tool", "tool": name, "state": {
                "status": "completed", "input": {"secret": "PRIVATE_INPUT_SENTINEL"},
                "output": "PRIVATE_OUTPUT_SENTINEL-á", "time": {"start": time, "end": time + 50},
            },
        })))

    def args(self, **updates):
        values = dict(database=self.path, since="1970-01-01T00:00:01Z", until="1970-01-01T00:00:03Z",
                      project_root=None, model=None)
        values.update(updates)
        return Namespace(**values)

    def capture_args(self, *extra):
        return metrics.build_parser().parse_args([
            "capture", "--session", "root", "--variant", "with-codegraph", "--pair-id", "p",
            "--project", "repo", "--task-kind", "review", "--policy-version", "policy-1",
            "--outcome", "accepted", "--state-dir", str(self.root / "state"),
            "--database", str(self.path), "--marker", str(self.root / "absent-marker"), *extra,
        ])

    def test_history_groups_linked_children_once_and_keeps_unrelated_family(self):
        report = telemetry.history_report(self.args())
        self.assertEqual(report["families"], 2)
        graph = next(g for g in report["groups"] if g["cohort"] == "with-codegraph")
        self.assertEqual(graph["metrics"]["tokens_total"]["median"], 300)
        self.assertEqual(graph["metrics"]["linked_sessions"]["median"], 3)
        self.assertEqual(graph["metrics"]["assistant_work_ms"]["median"], 3000)
        self.assertEqual(graph["metrics"]["assistant_active_union_ms"]["median"], 1200)
        self.assertEqual(graph["metrics"]["codegraph_latency_ms"]["median"], 50)
        self.assertIsNone(graph["acceptance_rate"])
        text = json.dumps(report) + telemetry.history_markdown(report)
        for secret in ("PRIVATE_PROMPT", "PRIVATE_INPUT", "PRIVATE_OUTPUT", "/private/work", "root-msg"):
            self.assertNotIn(secret, text)

    def test_readonly_and_invalid_database_does_not_create_file(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with telemetry.read_database(self.path) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM session")
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        missing = self.root / "missing.db"
        with self.assertRaises(FileNotFoundError):
            with telemetry.read_database(missing):
                pass
        self.assertFalse(missing.exists())

    def test_history_until_exclusive_and_invalid_date_range(self):
        report = telemetry.history_report(self.args(until="1970-01-01T00:00:01.400Z"))
        self.assertEqual(report["families"], 1)
        with self.assertRaises(ValueError):
            telemetry.history_report(self.args(since="2026-10-25", until="2026-10-24"))

    def test_missing_native_total_does_not_disappear_into_zero(self):
        self.add_message("other", "missing-total", 1500, missing=True)
        self.db.commit()
        report = telemetry.history_report(self.args())
        group = next(g for g in report["groups"] if g["cohort"] == "without-codegraph")
        self.assertIsNone(group["metrics"]["tokens_total"]["median"])
        self.assertEqual(group["metrics"]["tokens_total"]["missing"], 1)
        self.assertEqual(group["metrics"]["tokens_input"]["median"], 160)

    def test_capture_requires_explicit_task_and_includes_descendants(self):
        with self.assertRaises(ValueError):
            telemetry.capture_metrics(self.capture_args())
        record, path = metrics.capture_record(self.capture_args("--dedicated-task"))
        self.assertEqual(record["metrics"]["tokens"]["total"], 300)
        self.assertEqual(record["scope"]["linked_sessions"], ["child", "grand", "root"])
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIsNone(record["evaluation"]["corrections_required"])
        self.assertNotIn("PRIVATE_", path.read_text())

    def test_capture_pair_roundtrip_reports_increased_cost_instead_of_assumed_savings(self):
        with_args = self.capture_args("--dedicated-task", "--utility", "yes")
        metrics.capture_record(with_args)
        without_args = self.capture_args("--dedicated-task", "--utility", "not-applicable")
        without_args.session = "other"
        without_args.variant = "without-codegraph"
        metrics.capture_record(without_args)
        report = metrics.build_report(metrics.load_records(self.root / "state"))
        self.assertEqual(report["complete_accepted_pairs"], 1)
        self.assertEqual(report["aggregate"]["total_tokens"]["paired_improvement_pct_median"], -200)
        self.assertEqual(report["strata"][0]["dimensions"]["policy_version"], "policy-1")
        self.assertIn("-200.0%", metrics.report_markdown(report))

    def test_capture_range_is_checked_and_child_events_are_time_bounded(self):
        args = self.capture_args("--from-message", "root-msg", "--to-message", "root-msg")
        data, scope = telemetry.capture_metrics(args)
        self.assertEqual(data["tokens"]["total"], 300)
        self.assertEqual(scope["boundary_kind"], "message-range")
        with self.assertRaises(ValueError):
            telemetry.capture_metrics(self.capture_args("--from-message", "root-msg"))
        with self.assertRaises(ValueError):
            telemetry.capture_metrics(self.capture_args("--from-message", "root-msg", "--to-message", "bad"))

    def test_model_filter_does_not_hide_child_with_different_model(self):
        self.add_message("child", "other-model-msg", 1600, model="other")
        self.db.commit()
        report = telemetry.history_report(self.args(model="provider/model"))
        self.assertEqual(report["families"], 1)
        self.assertEqual(report["groups"][0]["cohort"], "without-codegraph")

    def test_cycles_and_unknown_schema_fail_closed(self):
        self.db.execute("UPDATE session SET parent_id='grand' WHERE id='root'")
        self.db.commit()
        with self.assertRaises(ValueError):
            telemetry.history_report(self.args())
        invalid = self.root / "invalid.db"
        sqlite3.connect(invalid).close()
        with self.assertRaises(ValueError):
            with telemetry.read_database(invalid):
                pass

    def test_report_cannot_overwrite_its_database(self):
        args = self.args(output=self.path, json=True)
        with self.assertRaises(ValueError):
            metrics.command_history(args)

    def test_capture_rejects_negative_evaluation_and_empty_policy(self):
        with self.assertRaises(ValueError):
            telemetry.capture_metrics(self.capture_args("--dedicated-task", "--corrections-required", "-1"))
        args = self.capture_args("--dedicated-task")
        args.policy_version = " "
        with self.assertRaises(ValueError):
            telemetry.capture_metrics(args)


class MetricsInstallTest(unittest.TestCase):
    def test_metrics_only_preserves_functional_assets_without_a_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config"
            target.mkdir()
            protected = {
                "opencode.json": '{"mcp":{"sentinel":true}}',
                ".opencode-codegraph-addon.json": "marker-sentinel",
                "skills/codegraph-analisis-estructural/SKILL.md": "skill-sentinel",
                "agents/planner.md": "agent-sentinel",
            }
            for rel, text in protected.items():
                path = target / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            runtime = Path(tmp) / "absent-runtime"
            subprocess.run(["bash", str(REPO / "scripts/install.sh"), "--metrics-only",
                            "--target-dir", str(target), "--runtime-dir", str(runtime), "--no-validate"],
                           check=True, capture_output=True)
            self.assertFalse(runtime.exists())
            for rel, text in protected.items():
                self.assertEqual((target / rel).read_text(), text)
            self.assertTrue((target / "scripts/codegraph_telemetry.py").exists())
            self.assertFalse((target / "scripts/codegraph_project.py").exists())


if __name__ == "__main__":
    unittest.main()
