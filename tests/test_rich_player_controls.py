import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load_player_row_builders():
    path = ROOT / "music/AoiMusic/utils/rich_panels.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = {"_xeno_bar", "_autoplay_button", "_toggle_icon_button", "_rows"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]

    def rich_button(text, callback_data="", style="primary", emoji="", icon_only=False):
        return (
            f'<button data="{callback_data}" style="{style}" emoji="{emoji}" '
            f'icon-only="{int(icon_only)}">{text}</button>'
        )

    def rich_button_row(*buttons, align=""):
        return "<row>" + "".join(buttons) + "</row>"

    namespace = {
        "rich_button": rich_button,
        "rich_button_row": rich_button_row,
        "autoplay_cache": {},
        "BLANK_BTN_TEXT": "",
    }
    package = types.ModuleType("AoiMusic")
    package.__path__ = []
    utils = types.ModuleType("AoiMusic.utils")
    utils.__path__ = []
    formatters = types.ModuleType("AoiMusic.utils.formatters")
    formatters.seconds_to_min = lambda seconds: f"{seconds // 60:02d}:{seconds % 60:02d}"
    with patch.dict(
        sys.modules,
        {
            "AoiMusic": package,
            "AoiMusic.utils": utils,
            "AoiMusic.utils.formatters": formatters,
        },
    ):
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class RichPlayerControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builders = _load_player_row_builders()

    def test_legacy_player_buttons_are_kept_and_only_reordered(self):
        rows = self.builders["_rows"](123, "trackABC", 72, 240)
        self.assertEqual(rows.count("<row>"), 5)

        # Main transport icons: Pause, Skip, Replay, Stop.
        expected_controls = (
            'data="ADMIN Pp|123"',
            'data="ADMIN Skip|123"',
            'data="ADMIN Replay|123"',
            'data="ADMIN Stop|123"',
        )
        positions = [rows.index(callback) for callback in expected_controls]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(rows.count('icon-only="1"'), 4)

        # Keep the original secondary actions and labels; no new buttons added.
        for callback in (
            'data="add_playlist trackABC"',
            'data="AutoplayToggle|123"',
            'data="PanelMarkup trackABC|123"',
            'data="GetSuggestions|123"',
            'data="close"',
        ):
            with self.subTest(callback=callback):
                self.assertIn(callback, rows)
        self.assertLess(rows.index('data="PanelMarkup'), rows.index('data="GetSuggestions'))
        self.assertIn(">ᴘʟᴀʏʟɪsᴛ</button>", rows)
        self.assertIn(">ᴍᴇɴᴜ</button>", rows)
        self.assertNotIn("Save track", rows)
        self.assertNotIn("Queue", rows)

    def test_paused_player_keeps_the_same_layout_and_switches_to_play_icon(self):
        rows = self.builders["_rows"](123, "trackABC", 72, 240, playing=False)
        self.assertIn('data="ADMIN Pp|123" style="success" emoji="PLAY" icon-only="1"', rows)
        self.assertIn('data="ADMIN Skip|123"', rows)
        self.assertEqual(rows.count("<row>"), 5)


if __name__ == "__main__":
    unittest.main()
