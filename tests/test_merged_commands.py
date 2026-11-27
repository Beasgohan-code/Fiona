import ast
import asyncio
import json
from datetime import date, timedelta
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

    def test_collection_modes_sort_by_anime_recent_and_favorite(self):
        source_path = WAIFU / "modules/harem.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_sort_collection_characters"
        )
        namespace = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source_path), "exec"), namespace)
        sort_characters = namespace["_sort_collection_characters"]
        caught = [
            {"id": 2, "anime": "B"},
            {"id": 1, "anime": "A"},
            {"id": 2, "anime": "B"},
            {"id": 3, "anime": "A"},
        ]
        self.assertEqual(
            [item["id"] for item in sort_characters(caught, "anime")],
            [1, 3, 2, 2],
        )
        self.assertEqual(
            [item["id"] for item in sort_characters(caught, "recent")],
            [2, 1, 2, 3],
        )
        self.assertEqual(
            [item["id"] for item in sort_characters(caught, "fav", [2])],
            [2, 2, 1, 3],
        )

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
        self.assertIn("items_per_page = 10", harem)
        self.assertIn("owned_in_anime", harem)
        self.assertIn("latest_catch_order", harem)
        self.assertIn("collection_mode = (user_db or {}).get('collection_mode', 'anime')", harem)
        self.assertIn("filters.regex('^set_collection_mode:')", harem)
        self.assertIn("×{count}", harem)
        self.assertNotIn("rich_table(('ID', 'RARITY', 'CHARACTER', 'OWNED'), rows)", harem)
        self.assertIn("rich_table(\n            ('RARITY', 'CHARACTERS')", profile)

    def test_summon_compatible_commands_use_fiona_handlers_and_menu(self):
        registered = set(commands_in_tree(WAIFU, is_music=False))
        for name in ("spin", "achievements", "ach", "badges", "me", "hstats", "rarities", "server", "search", "claimlist", "summon", "streak", "panel", "pincharacter", "unpincharacter", "pinnedcharacters", "hpin", "hunpin", "pinlist", "fav"):
            self.assertIn(name, registered)
        private_names = {name for name, _ in PRIVATE_COMMANDS}
        for name in ("spin", "achievements", "me", "hstats", "rarity", "server", "search", "claimlist", "summon", "streak", "pincharacter", "unpincharacter", "pinnedcharacters"):
            self.assertIn(name, private_names)
        for legacy_name in ("hpin", "hunpin", "pinlist"):
            self.assertNotIn(legacy_name, private_names)
        spin = (WAIFU / "modules/spin.py").read_text(encoding="utf-8")
        self.assertIn("find_one_and_update", spin)
        self.assertIn("SPIN_COOLDOWN = timedelta(hours=24)", spin)
        self.assertNotIn("sqlite", spin.lower())

    def test_empty_admin_exports_send_a_notice_and_temp_files_are_isolated(self):
        import os
        import tempfile

        source_path = WAIFU / "admin/lists.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_export_document"
        )
        notices = []

        async def fake_notice(message, text):
            notices.append(text)

        namespace = {
            "os": os,
            "tempfile": tempfile,
            "reply_notice": fake_notice,
            "tr": lambda text, lang: text,
        }
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source_path), "exec"), namespace)
        send_export = namespace["_send_export_document"]

        class FakeMessage:
            def __init__(self):
                self.sent_path = None
                self.content = None

            async def reply_document(self, document):
                self.sent_path = document
                self.content = Path(document).read_text(encoding="utf-8")
                self.assert_nonempty = os.path.getsize(document) > 0

        empty_message = FakeMessage()
        asyncio.run(send_export(empty_message, [], "en", "Nothing to export.", "fiona-empty-"))
        self.assertEqual(notices, ["Nothing to export."])
        self.assertIsNone(empty_message.sent_path)

        populated_message = FakeMessage()
        asyncio.run(send_export(populated_message, ["Group One (-1001)", "Group Two (-1002)"], "en", "Empty.", "fiona-groups-"))
        self.assertEqual(populated_message.content, "Group One (-1001)\nGroup Two (-1002)")
        self.assertTrue(populated_message.assert_nonempty)
        self.assertFalse(os.path.exists(populated_message.sent_path))

    def test_daily_reward_streak_is_persisted_and_localized(self):
        balance_path = WAIFU / "modules/balance.py"
        source = balance_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        helpers = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_as_date", "_daily_streak_after_claim"}
        ]
        module = ast.Module(
            body=[ast.ImportFrom(module="datetime", names=[ast.alias(name="date"), ast.alias(name="datetime"), ast.alias(name="timedelta")], level=0), *helpers],
            type_ignores=[],
        )
        ast.fix_missing_locations(module)
        namespace = {}
        exec(compile(module, str(balance_path), "exec"), namespace)
        today = date(2026, 11, 26)
        streak = namespace["_daily_streak_after_claim"]
        self.assertEqual(streak(today - timedelta(days=1), 4, today), 5)
        self.assertEqual(streak(today - timedelta(days=2), 4, today), 1)
        self.assertEqual(streak("2026-11-25T20:00:00", 2, today), 3)
        self.assertIn('filters.command("streak")', source)
        self.assertIn('"longest_daily_streak": best_streak', source)
        for locale in (WAIFU / "langs").glob("*.json"):
            data = json.loads(locale.read_text(encoding="utf-8"))
            for key in ("daily_reward_title", "daily_streak_line", "streak_current", "streak_best", "streak_hint"):
                self.assertIn(key, data, f"Missing {key} from {locale}")

    def test_plain_waifu_replies_use_the_shared_richgram_notice(self):
        wrapped = 0
        edited = 0
        for directory in (WAIFU / "modules", WAIFU / "admin"):
            for path in directory.glob("*.py"):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    if isinstance(node.func, ast.Name) and node.func.id == "reply_notice":
                        wrapped += 1
                    if isinstance(node.func, ast.Name) and node.func.id == "edit_notice":
                        edited += 1
                    if isinstance(node.func, ast.Attribute) and node.func.attr in {"reply_text", "edit_text", "reply"}:
                        payload = node.args[0] if node.args else None
                        if (
                            not any(keyword.arg == "parse_mode" for keyword in node.keywords)
                            and isinstance(payload, ast.Call)
                            and isinstance(payload.func, ast.Name)
                            and payload.func.id in {"tr", "t"}
                        ):
                            self.fail(f"Unstyled {node.func.attr} in {path.name}:{node.lineno}")
        self.assertGreaterEqual(wrapped, 150)
        self.assertGreaterEqual(edited, 10)
        ui = (WAIFU / "unit/rich_ui.py").read_text(encoding="utf-8")
        self.assertIn("def notice_card(", ui)
        self.assertIn("rich_esc(body)", ui)
        self.assertIn("async def reply_notice(", ui)

    def test_collection_ui_uses_open_rich_layouts_without_box_art(self):
        ui = (WAIFU / "unit/rich_ui.py").read_text(encoding="utf-8")
        self.assertIn("bullet separators", ui)
        self.assertIn("borderless Fiona panel", ui)
        forbidden = re.compile(r"[╭╮╯╰╔╗╚╝┏┓┗┛┌┐└┘├┤┬┴┼╋━═─│〔〕]")
        for source in list((WAIFU / "modules").glob("*.py")) + list((WAIFU / "admin").glob("*.py")):
            contents = source.read_text(encoding="utf-8")
            self.assertNotRegex(contents, forbidden, str(source))
        spin = (WAIFU / "modules/spin.py").read_text(encoding="utf-8")
        self.assertIn("rich_quote(", spin)
        self.assertNotIn('("PLAYER", "RESULT")', spin)
        for locale in (WAIFU / "langs").glob("*.json"):
            data = json.loads(locale.read_text(encoding="utf-8"))
            self.assertNotRegex(json.dumps(data, ensure_ascii=False), forbidden, str(locale))
            start_caption = data.get("start_private_caption", "")
            self.assertFalse(
                any("dressup" in line.lower() and line.lstrip().startswith("•") for line in start_caption.splitlines()),
                f"Dress-Up promo bullet remains in {locale}",
            )

    def test_profile_uses_generated_card_and_keeps_photo_fallback(self):
        profile = (WAIFU / "modules/stats.py").read_text(encoding="utf-8")
        card = (WAIFU / "unit/profile_card.py").read_text(encoding="utf-8")
        self.assertIn("build_profile_card(stats)", profile)
        self.assertIn('photo=stats["photo_url"] or STATS_IMG[0]', profile)
        self.assertIn('image.save(output, format="PNG", optimize=True)', card)
        self.assertIn("COLLECTION PROGRESS", card)

    def test_owner_command_is_private_and_owner_id_gated(self):
        owner = (WAIFU / "modules/owner.py").read_text(encoding="utf-8")
        self.assertIn('filters.command(["owner", "panel"]) & filters.private', owner)
        self.assertIn("message.from_user.id != OWNER_ID", owner)
        self.assertNotIn('("owner",', (ROOT / "unified_commands.py").read_text(encoding="utf-8"))
        merged = (ROOT / "merged.py").read_text(encoding="utf-8")
        self.assertIn('("owner", "Open owner tools")', merged)
        self.assertIn("BotCommandScopeChat(chat_id=OWNER_ID)", merged)

    def test_missing_origin_chat_is_guarded_before_rich_send(self):
        rich_msg = (MUSIC / "utils/rich_msg.py").read_text(encoding="utf-8")
        autoplay = (MUSIC / "plugins/play/autoplay.py").read_text(encoding="utf-8")
        send_body = rich_msg.split("async def send_rich(", 1)[1].split("async def edit_rich(", 1)[0]
        self.assertIn("if chat_id == 0:", send_body)
        self.assertIn("return None", send_body)
        self.assertIn("if not original_chat_id:", autoplay)
        self.assertIn("show_alert=True", autoplay)

    def test_major_waifu_cards_share_rich_text_and_premium_controls(self):
        modules = ("shop", "trade", "gift", "fav", "check", "guess", "rank", "leaderboard", "balance", "sips", "addchar", "referral", "hclaim", "gen", "rarity", "total", "ping", "lang")
        for module in modules:
            source = (WAIFU / f"modules/{module}.py").read_text(encoding="utf-8")
            self.assertIn("rich_ui", source, f"{module} should use shared card rendering")
            self.assertIn("premium_text", source, f"{module} should decorate card text")
        inline_query = (WAIFU / "modules/inlinequery.py").read_text(encoding="utf-8")
        self.assertIn("rich_card", inline_query)
        self.assertIn("rich_table", inline_query)
        self.assertIn("premium_text", inline_query)

    def test_help_uses_the_unified_waifu_command_names(self):
        help_data = waifu_help_data()
        help_text = "\\n".join(
            value
            for entry in help_data.values()
            for key, value in entry.items()
            if key == "HELP" or key.startswith("HELP_")
        )
        self.assertIn("`/pincharacter <id>`", help_text)
        self.assertIn("`/unpincharacter <id>`", help_text)
        self.assertIn("`/pinnedcharacters`", help_text)
        self.assertIn("Sort by anime, newest catch, or favorite", help_text)
        self.assertIn("`/hpin`", help_text)
        self.assertIn("`/hunpin`", help_text)
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
            WAIFU / "modules/hclaim.py",
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
