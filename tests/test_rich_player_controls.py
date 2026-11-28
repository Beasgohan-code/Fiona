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
    wanted = {"_xeno_bar", "_autoplay_button", "_toggle_button", "_rows"}
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
        "db": {},
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

    def test_main_controls_are_labeled_and_keep_existing_callbacks(self):
        rows = self.builders["_rows"](123, "trackABC", 72, 240)
        for label in ("Pause", "Replay", "Skip", "Stop", "Queue", "Save track", "Autoplay Off", "Suggestions", "More controls", "Close"):
            with self.subTest(label=label):
                self.assertIn(f">{label}</button>", rows)
        for callback in (
            "ADMIN Pp|123",
            "ADMIN Replay|123",
            "ADMIN Skip|123",
            "ADMIN Stop|123",
            "GetQueued 123|trackABC",
            "add_playlist trackABC",
            "AutoplayToggle|123",
            "GetSuggestions|123",
            "PanelMarkup trackABC|123",
            "data=\"close\"",
        ):
            with self.subTest(callback=callback):
                self.assertIn(callback, rows)
        self.assertEqual(rows.count("<row>"), 4)
        self.assertNotIn('icon-only="1"', rows)

    def test_paused_player_offers_resume_and_hides_non_youtube_save_action(self):
        rows = self.builders["_rows"](123, "telegram", 72, 240, playing=False)
        self.assertIn(">Resume</button>", rows)
        self.assertNotIn(">Pause</button>", rows)
        self.assertNotIn("add_playlist", rows)
        self.assertIn("GetQueued 123|telegram", rows)


if __name__ == "__main__":
    unittest.main()
