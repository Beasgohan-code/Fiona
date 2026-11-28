import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "waifu/aoiwaifu/modules/checkspawn.py"


def load_spawn_progress():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_spawn_progress"
    )
    namespace = {"_DEFAULT_SPAWN_LIMIT": 80}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(MODULE), "exec"), namespace)
    return namespace["_spawn_progress"]


class CheckSpawnTests(unittest.TestCase):
    def test_progress_reports_count_remaining_and_percentage(self):
        self.assertEqual(load_spawn_progress()(25, 100), (25, 100, 75, 25))

    def test_progress_clamps_counter_and_handles_invalid_values(self):
        progress = load_spawn_progress()
        self.assertEqual(progress(120, 80), (80, 80, 0, 100))
        self.assertEqual(progress(-5, 80), (0, 80, 80, 0))
        self.assertEqual(progress("bad", "bad"), (0, 80, 80, 0))

    def test_group_command_is_registered_and_documented(self):
        source = MODULE.read_text(encoding="utf-8")
        commands = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        help_source = (ROOT / "waifu/aoiwaifu/unit/aoi_help.py").read_text(encoding="utf-8")
        self.assertIn('filters.command(["checkspawn"]) & filters.group', source)
        self.assertIn('("checkspawn", "Check character spawn threshold and progress")', commands)
        self.assertIn("`/checkspawn`", help_source)


if __name__ == "__main__":
    unittest.main()
