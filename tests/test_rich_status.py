import ast
import asyncio
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RICH_MSG = ROOT / "music/AoiMusic/utils/rich_msg.py"


class RichStatusTests(unittest.TestCase):
    def test_fiona_notice_uses_native_richgram_and_keeps_editable_message_result(self):
        ui_file = ROOT / "waifu/aoiwaifu/unit/rich_ui.py"
        tree = ast.parse(ui_file.read_text(encoding="utf-8"))
        rich_reply_helper = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_rich_reply"
        )
        reply_notice = next(
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "reply_notice"
        )
        sends = []
        expected_message = types.SimpleNamespace(id=902)

        async def send_rich(chat_id, body, **kwargs):
            sends.append((chat_id, body, kwargs))
            return 902

        async def edit_rich(*args, **kwargs):
            return True

        class FakeClient:
            async def get_messages(self, chat_id, message_id):
                self.lookup = (chat_id, message_id)
                return expected_message

        namespace = {
            "send_rich": send_rich,
            "edit_rich": edit_rich,
            "richgram_notice_card": lambda text, **kwargs: f"<h4>Fiona</h4><blockquote>{text}</blockquote>",
            "notice_card": lambda text, **kwargs: text,
            "ParseMode": types.SimpleNamespace(HTML="html"),
            "SimpleNamespace": types.SimpleNamespace,
        }
        exec(compile(ast.Module(body=[rich_reply_helper, reply_notice], type_ignores=[]), str(ui_file), "exec"), namespace)
        message = types.SimpleNamespace(
            chat=types.SimpleNamespace(id=-100123),
            id=456,
            _client=FakeClient(),
        )
        result = asyncio.run(namespace["reply_notice"](
            message,
            "All done",
            reply_markup="keyboard",
        ))

        self.assertIs(result, expected_message)
        self.assertEqual(sends[0][0], -100123)
        self.assertIn("<blockquote>", sends[0][1])
        self.assertEqual(sends[0][2], {"reply_markup": "keyboard", "reply_to": 456})
        self.assertEqual(message._client.lookup, (-100123, 902))

    def test_all_collection_message_replies_use_shared_richgram_helpers(self):
        roots = (ROOT / "waifu/aoiwaifu/modules", ROOT / "waifu/aoiwaifu/admin")
        direct_replies = []
        for root in roots:
            for path in root.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr not in {"reply_text", "reply_photo", "reply_video"}:
                        continue
                    target = ast.unparse(node.func.value)
                    if target in {"message", "callback_query.message", "query.message"}:
                        direct_replies.append(f"{path}:{node.lineno} {target}.{node.func.attr}")
        self.assertEqual(direct_replies, [])

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
