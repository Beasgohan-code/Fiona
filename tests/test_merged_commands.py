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
HELP_FILE = ROOT / "waifu/aoiwaifu/unit/aoi_help.py"


def waifu_help_data():
    tree = ast.parse(HELP_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "HELP_DATA"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("HELP_DATA definition not found")


def premium_emoji_keys():
    registry = MUSIC / "utils/premium_emoji.py"
    tree = ast.parse(registry.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "PREMIUM_EMOJIS":
            return set(ast.literal_eval(node.value))
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PREMIUM_EMOJIS"
            for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("PREMIUM_EMOJIS registry not found")


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

    def test_telegram_menus_have_unique_names_and_fit_api_limit(self):
        for commands in (PRIVATE_COMMANDS, GROUP_COMMANDS, ADMIN_COMMANDS):
            names = [name for name, _ in commands]
            self.assertEqual(len(names), len(set(names)))
            self.assertLessEqual(len(commands), 100)

    def test_advertised_group_and_admin_commands_are_registered(self):
        music = commands_in_tree(MUSIC, is_music=True)
        waifu = commands_in_tree(WAIFU, is_music=False)
        registered = set(music) | set(waifu)
        for scope, commands in (("group", GROUP_COMMANDS), ("admin", ADMIN_COMMANDS)):
            missing = sorted(name for name, _ in commands if name not in registered)
            self.assertEqual(missing, [], f"Unregistered {scope} commands: {missing}")
        self.assertIn("grouphelp", {name for name, _ in GROUP_COMMANDS})

    def test_group_start_panel_opens_group_management_guide(self):
        start = (WAIFU / "modules/start.py").read_text(encoding="utf-8")
        group_tools = (MUSIC / "plugins/manage/group_utils.py").read_text(encoding="utf-8")
        self.assertIn('callback_data="grouphelp:open"', start)
        self.assertIn("grouphelp:(open|home|moderation|setup|safety|tools)", group_tools)

    def test_group_management_guide_references_real_commands_and_emojis(self):
        guide_path = MUSIC / "plugins/manage/group_utils.py"
        tree = ast.parse(guide_path.read_text(encoding="utf-8"))
        guide = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_GROUP_HELP" for target in node.targets)
        )
        registered = set(commands_in_tree(MUSIC, is_music=True))
        emoji_keys = premium_emoji_keys()
        for title, emoji, text in guide.values():
            self.assertIn(emoji, emoji_keys)
            for name in re.findall(r"<code>/([a-z0-9_]+)</code>", text):
                self.assertIn(name, registered, f"Guide command /{name} has no handler")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "rich_button":
                emoji = next(
                    (
                        kw.value.value
                        for kw in node.keywords
                        if kw.arg == "emoji" and isinstance(kw.value, ast.Constant)
                    ),
                    None,
                )
                if emoji:
                    self.assertIn(emoji, emoji_keys)

    def test_harem_and_profile_use_shared_rich_ui_without_timed_message_deletion(self):
        harem = (WAIFU / "modules/harem.py").read_text(encoding="utf-8")
        profile = (WAIFU / "modules/stats.py").read_text(encoding="utf-8")
        for source in (harem, profile):
            self.assertIn("premium_button", source)
            self.assertIn("premium_text", source)
        self.assertIn("edit_panel", harem)
        self.assertIn("edit_panel", profile)
        self.assertNotIn("asyncio.sleep(180)", harem)
        self.assertIn("premium_button(\n                        tr('Next', lang)", harem)

    def test_missing_origin_chat_is_guarded_before_rich_send(self):
        rich_msg = (MUSIC / "utils/rich_msg.py").read_text(encoding="utf-8")
        autoplay = (MUSIC / "plugins/play/autoplay.py").read_text(encoding="utf-8")
        send_body = rich_msg.split("async def send_rich(", 1)[1].split("async def edit_rich(", 1)[0]
        self.assertIn("if chat_id == 0:", send_body)
        self.assertIn("return None", send_body)
        self.assertIn("if not original_chat_id:", autoplay)
        self.assertIn("show_alert=True", autoplay)

    def test_major_waifu_cards_share_rich_text_and_premium_controls(self):
        modules = ("shop", "trade", "gift", "fav", "check", "guess", "rank", "leaderboard", "balance", "sips", "addchar", "referral")
        for module in modules:
            source = (WAIFU / f"modules/{module}.py").read_text(encoding="utf-8")
            self.assertIn("rich_ui", source, f"{module} should use shared card rendering")
            self.assertIn("premium_text", source, f"{module} should decorate card text")

    def test_help_uses_the_unified_waifu_command_names(self):
        help_data = waifu_help_data()
        help_text = "\\n".join(
            value
            for entry in help_data.values()
            for key, value in entry.items()
            if key == "HELP" or key.startswith("HELP_")
        )
        self.assertIn("`/hpin <id>`", help_text)
        self.assertIn("`/hunpin <id>`", help_text)
        self.assertNotIn("`/pin <id>`", help_text)
        self.assertNotIn("`/stats`", help_text)
        self.assertNotIn("`/eval`", help_text)

    def test_waifu_start_and_help_use_shared_rich_ui_helpers(self):
        start = (WAIFU / "modules/start.py").read_text(encoding="utf-8")
        rich_ui = (WAIFU / "unit/rich_ui.py").read_text(encoding="utf-8")
        self.assertIn("premium_button", start)
        self.assertIn("premium_text", start)
        self.assertIn("edit_panel", start)
        self.assertIn("premiumize_html", rich_ui)

    def test_waifu_help_callback_namespace_does_not_overlap_music_help(self):
        start = (WAIFU / "modules/start.py").read_text(encoding="utf-8")
        self.assertIn('callback_data=f"waifuhelp:{module_name}"', start)
        self.assertIn('filters.regex(r"^waifuhelp:([a-z0-9_]+)$")', start)
        self.assertNotIn('filters.regex("^help_(.+)")', start)

    def test_waifu_premium_button_icons_exist_in_registry(self):
        keys = premium_emoji_keys()
        for path in (
            WAIFU / "modules/start.py",
            WAIFU / "modules/harem.py",
            WAIFU / "modules/stats.py",
            WAIFU / "modules/shop.py",
            WAIFU / "modules/trade.py",
            WAIFU / "modules/gift.py",
            WAIFU / "modules/fav.py",
            WAIFU / "modules/check.py",
            WAIFU / "modules/guess.py",
            WAIFU / "modules/rank.py",
            WAIFU / "modules/sips.py",
            WAIFU / "modules/addchar.py",
            WAIFU / "modules/referral.py",
            WAIFU / "unit/aoi_lang.py",
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "emoji" and isinstance(keyword.value, ast.Constant):
                        self.assertIn(keyword.value.value, keys, f"{path.name}: {keyword.value.value}")

    def test_group_registry_and_event_log_failures_are_contained(self):
        registry_source = (WAIFU / "modules/joinlog.py").read_text(encoding="utf-8")
        sender_source = (WAIFU / "unit/event_logger.py").read_text(encoding="utf-8")
        for source, function_names in (
            (registry_source, {"mark_group_active", "mark_group_inactive"}),
            (sender_source, {"send_event_log"}),
        ):
            tree = ast.parse(source)
            helpers = [
                node
                for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name in function_names
            ]
            self.assertEqual({node.name for node in helpers}, function_names)
            for helper in helpers:
                self.assertTrue(any(isinstance(node, ast.Try) for node in ast.walk(helper)))
                self.assertTrue(
                    any(
                        isinstance(node, ast.Return)
                        and isinstance(node.value, ast.Constant)
                        and node.value.value is False
                        for node in ast.walk(helper)
                    )
                )
        self.assertIn("active", registry_source)

    def test_shared_start_alias_is_waifu_and_standard_start_is_music_router(self):
        start = (MUSIC / "plugins/bot/start.py").read_text(encoding="utf-8")
        self.assertIn('name.lower() == "waifu"', start)
        waifu_start = (WAIFU / "modules/start.py").read_text(encoding="utf-8")
        self.assertIn('filters.command("waifu")', waifu_start)
        self.assertNotIn('filters.command("start")', waifu_start)


if __name__ == "__main__":
    unittest.main()
