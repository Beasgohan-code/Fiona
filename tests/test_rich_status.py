import ast
import asyncio
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RICH_MSG = ROOT / "music/AoiMusic/utils/rich_msg.py"


class RichStatusTests(unittest.TestCase):
    def test_rich_mystic_falls_back_to_plain_edit_when_rich_edit_fails(self):
        tree = ast.parse(RICH_MSG.read_text(encoding="utf-8"))
        rich_mystic = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "RichMystic"
        )
        edit_method = next(
            node for node in rich_mystic.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "edit_text"
        )
        edits = []

        class FakeClient:
            async def edit_message_text(self, **kwargs):
                edits.append(kwargs)

        class FakeLogger:
            def warning(self, *args, **kwargs):
                raise AssertionError("fallback should not fail")

        async def fail_rich_edit(*args, **kwargs):
            return False

        namespace = {
            "edit_rich": fail_rich_edit,
            "_style_status": lambda text: f"rich:{text}",
            "_client": lambda: FakeClient(),
            "_no_preview_kwargs": lambda: {"disable_web_page_preview": True},
            "log": FakeLogger(),
        }
        exec(compile(ast.Module(body=[edit_method], type_ignores=[]), str(RICH_MSG), "exec"), namespace)
        status = types.SimpleNamespace(chat_id=-100123, id=456)
        result = asyncio.run(namespace["edit_text"](status, "Playback failed"))

        self.assertTrue(result)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["chat_id"], -100123)
        self.assertEqual(edits[0]["message_id"], 456)
        self.assertEqual(edits[0]["text"], "Playback failed")
        self.assertIsNone(edits[0]["parse_mode"])
        self.assertTrue(edits[0]["disable_web_page_preview"])


if __name__ == "__main__":
    unittest.main()
