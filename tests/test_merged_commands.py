import ast
import re
import unittest
from collections import defaultdict
from pathlib import Path

from unified_commands import ADMIN_COMMANDS, GROUP_COMMANDS, PRIVATE_COMMANDS

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "music/AoiMusic"
WAIFU = ROOT / "waifu/aoiwaifu"
MUSIC_COMMANDS_DIR = ROOT / "music/strings/cmds"


def music_aliases():
    aliases = defaultdict(set)
    for source in MUSIC_COMMANDS_DIR.glob("*.yml"):
        for line in source.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Z0-9_]+)\s*:\s*(\[.*\])\s*$", line)
            if match:
                aliases[match.group(1)].update(name.lower() for name in ast.literal_eval(match.group(2)))
    return {name: sorted(values) for name, values in aliases.items()}


def commands_in_tree(root: Path, is_music: bool):
    found = defaultdict(list)
    aliases = music_aliases() if is_music else {}
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if is_music and relative == "plugins/sudo/dev.py":
            continue
        if not is_music and relative in {"modules/ping.py", "admin/eval.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            names = []
            if isinstance(node.func, ast.Attribute) and node.func.attr == "command":
                try:
                    value = ast.literal_eval(node.args[0])
                    names = value if isinstance(value, (list, tuple)) else [value]
                except (ValueError, TypeError):
                    pass
            elif is_music and isinstance(node.func, ast.Name) and node.func.id == "command":
                try:
                    names = aliases.get(ast.literal_eval(node.args[0]), [])
                except (ValueError, TypeError):
                    pass
            for name in names:
                if isinstance(name, str):
                    found[name.lower()].append(f"{relative}:{node.lineno}")
    return found


class MergedCommandTests(unittest.TestCase):
    def test_cross_feature_command_names_do_not_overlap(self):
        music = commands_in_tree(MUSIC, is_music=True)
        waifu = commands_in_tree(WAIFU, is_music=False)
        duplicates = sorted(set(music) & set(waifu))
        details = [f"/{name}: music={music[name]}, waifu={waifu[name]}" for name in duplicates]
        self.assertEqual(duplicates, [], "\n".join(details))

    def test_telegram_menus_have_unique_names_per_scope(self):
        for commands in (PRIVATE_COMMANDS, GROUP_COMMANDS, ADMIN_COMMANDS):
            names = [name for name, _ in commands]
            self.assertEqual(len(names), len(set(names)))

    def test_shared_start_alias_is_waifu_and_standard_start_is_music_router(self):
        start = (MUSIC / "plugins/bot/start.py").read_text(encoding="utf-8")
        self.assertIn('name.lower() == "waifu"', start)
        waifu_start = (WAIFU / "modules/start.py").read_text(encoding="utf-8")
        self.assertIn('filters.command("waifu")', waifu_start)
        self.assertNotIn('filters.command("start")', waifu_start)


if __name__ == "__main__":
    unittest.main()
