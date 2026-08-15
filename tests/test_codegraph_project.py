from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "codegraph_project.py"
SPEC = importlib.util.spec_from_file_location("codegraph_project", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CodeGraphProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, capture_output=True)
        os.environ["OPENCODE_CODEGRAPH_ALLOW_TEMP"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("OPENCODE_CODEGRAPH_ALLOW_TEMP", None)
        self.tmp.cleanup()

    def test_resolve_and_exclude_are_idempotent(self) -> None:
        self.assertEqual(MODULE.resolve_root(str(self.root)), self.root.resolve())
        exclude = MODULE.ensure_exclude(self.root)
        MODULE.ensure_exclude(self.root)
        self.assertEqual(exclude.read_text().splitlines().count(".codegraph/"), 1)

    def test_symlinked_index_is_rejected(self) -> None:
        target = Path(self.tmp.name) / "elsewhere"
        target.mkdir()
        (self.root / ".codegraph").symlink_to(target, target_is_directory=True)
        with self.assertRaises(SystemExit):
            MODULE.resolve_root(str(self.root))

    def test_status_validation_refuses_reindex(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.validate_status(
                {
                    "initialized": True,
                    "index": {
                        "reindexRecommended": True,
                        "builtWithExtractionVersion": 23,
                        "currentExtractionVersion": 24,
                    },
                }
            )

    def test_registry_is_atomic_and_keyed_by_root(self) -> None:
        registry = Path(self.tmp.name) / "state" / "projects.json"
        status = {
            "initialized": True,
            "version": "1.5.0",
            "indexPath": str(self.root / ".codegraph"),
            "lastIndexed": "2026-08-15T00:00:00Z",
            "index": {"builtWithVersion": "1.5.0", "reindexRecommended": False},
        }
        MODULE.record_project(registry, self.root.resolve(), status)
        data = json.loads(registry.read_text())
        self.assertIn(str(self.root.resolve()), data["projects"])


if __name__ == "__main__":
    unittest.main()
