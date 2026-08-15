from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "manage_opencode_config.py"
SPEC = importlib.util.spec_from_file_location("manage_opencode_config", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ManageConfigTest(unittest.TestCase):
    def test_apply_and_remove_owned_fields(self) -> None:
        config = {"$schema": "https://opencode.ai/config.json", "provider": {"x": {}}}
        marker = {}
        binary = "/managed/codegraph"
        config, marker = MODULE.apply(config, marker, binary)
        self.assertEqual(config["mcp"]["codegraph"], MODULE.expected_mcp(binary))
        self.assertFalse(config["tools"][MODULE.TOOL_PATTERN])
        for name in MODULE.AGENTS:
            self.assertTrue(config["agent"][name]["tools"][MODULE.TOOL_PATTERN])

        result = MODULE.remove(config, marker, binary)
        self.assertNotIn("codegraph", result.get("mcp", {}))
        self.assertNotIn(MODULE.TOOL_PATTERN, result.get("tools", {}))
        self.assertEqual(result["provider"], {"x": {}})

    def test_apply_refuses_incompatible_existing_mcp(self) -> None:
        config = {"mcp": {"codegraph": {"type": "remote", "url": "https://example.test"}}}
        with self.assertRaises(SystemExit):
            MODULE.apply(config, {}, "/managed/codegraph")

    def test_uninstall_preserves_modified_owned_mcp(self) -> None:
        binary = "/managed/codegraph"
        config, marker = MODULE.apply({}, {}, binary)
        config["mcp"]["codegraph"]["enabled"] = False
        result = MODULE.remove(config, marker, binary)
        self.assertIn("codegraph", result["mcp"])


if __name__ == "__main__":
    unittest.main()
