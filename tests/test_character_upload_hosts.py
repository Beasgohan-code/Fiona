import ast
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_FILE = ROOT / "waifu/aoiwaifu/admin/upload.py"
CONFIG_FILE = ROOT / "waifu/aoiwaifu/config.py"


def load_catbox_uploader(requests):
    tree = ast.parse(UPLOAD_FILE.read_text(encoding="utf-8"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "upload_to_catbox"
    )
    namespace = {"os": os, "requests": requests, "urlparse": urlparse}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(UPLOAD_FILE), "exec"), namespace)
    return namespace["upload_to_catbox"]


def load_chat_target_parser():
    tree = ast.parse(CONFIG_FILE.read_text(encoding="utf-8"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_chat_target"
    )
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(CONFIG_FILE), "exec"), namespace)
    return namespace["_parse_chat_target"]


def load_character_channel_validator():
    tree = ast.parse(UPLOAD_FILE.read_text(encoding="utf-8"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "character_channel_target_error"
    )
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(UPLOAD_FILE), "exec"), namespace)
    return namespace["character_channel_target_error"]


def load_character_upload_error_formatter():
    tree = ast.parse(UPLOAD_FILE.read_text(encoding="utf-8"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "format_character_upload_error"
    )
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(UPLOAD_FILE), "exec"), namespace)
    return namespace["format_character_upload_error"]


def load_character_url_validator():
    tree = ast.parse(UPLOAD_FILE.read_text(encoding="utf-8"))
    host_assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CHARACTER_IMAGE_HOSTS" for target in node.targets)
    )
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_character_image_url"
    )
    namespace = {"urlparse": urlparse}
    exec(compile(ast.Module(body=[host_assignment, helper], type_ignores=[]), str(UPLOAD_FILE), "exec"), namespace)
    return namespace["require_character_image_url"]


class CatboxUploadTests(unittest.TestCase):
    def test_catbox_upload_returns_validated_files_url(self):
        calls = []

        class Response:
            status_code = 200
            text = "https://files.catbox.moe/abc123.jpg\n"

        class Requests:
            @staticmethod
            def post(url, **kwargs):
                calls.append((url, kwargs))
                return Response()

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            image.write(b"image-bytes")
            image.flush()
            result = load_catbox_uploader(Requests)(image.name)

        self.assertEqual(result, "https://files.catbox.moe/abc123.jpg")
        self.assertEqual(calls[0][0], "https://catbox.moe/user/api.php")
        self.assertEqual(calls[0][1]["data"], {"reqtype": "fileupload"})
        self.assertIn("fileToUpload", calls[0][1]["files"])

    def test_catbox_upload_rejects_non_catbox_response(self):
        class Response:
            status_code = 200
            text = "https://example.com/not-an-image"

        class Requests:
            @staticmethod
            def post(*args, **kwargs):
                return Response()

        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            image.write(b"image-bytes")
            image.flush()
            with self.assertRaisesRegex(Exception, "invalid image URL"):
                load_catbox_uploader(Requests)(image.name)

    def test_chat_destination_numeric_ids_are_parsed_as_integer_peers(self):
        parse_target = load_chat_target_parser()
        self.assertEqual(parse_target("-1001234567890"), -1001234567890)
        self.assertEqual(parse_target("@fiona_characters"), "@fiona_characters")

    def test_invalid_positive_or_phone_destination_is_rejected_before_upload(self):
        validate_target = load_character_channel_validator()
        self.assertIn("numeric chat ID", validate_target(123456789))
        self.assertIn("phone number", validate_target("+123456789"))
        self.assertEqual(validate_target(-1001234567890), "")
        self.assertEqual(validate_target("@fiona_characters"), "")

    def test_phone_resolution_failure_has_actionable_channel_setup_guidance(self):
        format_error = load_character_upload_error_formatter()
        message = format_error(Exception('BOT_METHOD_INVALID (caused by "contacts.ResolvePhone")'))
        self.assertIn("CHARA_CHANNEL_ID", message)
        self.assertIn("-100", message)
        self.assertIn("@channel username", message)
        self.assertNotIn("contacts.ResolvePhone", message)

    def test_direct_image_url_validation_allows_only_supported_https_hosts(self):
        validate = load_character_url_validator()
        self.assertEqual(
            validate("https://files.catbox.moe/abc.jpg"),
            "https://files.catbox.moe/abc.jpg",
        )
        self.assertEqual(validate("https://i.ibb.co/abc.jpg"), "https://i.ibb.co/abc.jpg")
        endtrz_url = "https://endtrz.vercel.app/1f17d589.jpg"
        self.assertEqual(validate(endtrz_url), endtrz_url)
        for url in (
            "http://files.catbox.moe/abc.jpg",
            "https://files.catbox.moe.evil.test/abc.jpg",
            "https://example.test/abc.jpg",
            "https://user:pass@i.ibb.co/abc.jpg",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate(url)

    def test_upload_command_offers_each_host_and_sends_to_character_channel(self):
        source = UPLOAD_FILE.read_text(encoding="utf-8")
        self.assertIn('InlineKeyboardButton("ImgBB", callback_data=f"gupload:{token}:imgbb")', source)
        self.assertIn('InlineKeyboardButton("Catbox", callback_data=f"gupload:{token}:catbox")', source)
        self.assertIn("@ZYRO.on_callback_query", source)
        self.assertIn("chat_id=CHARA_CHANNEL_ID", source)
        self.assertIn('"img_url": file_url', source)

        addchar_source = (ROOT / "waifu/aoiwaifu/modules/addchar.py").read_text(encoding="utf-8")
        self.assertIn('InlineKeyboardButton("ImgBB", callback_data=f"addcharhost:{token}:imgbb")', addchar_source)
        self.assertIn('InlineKeyboardButton("Catbox", callback_data=f"addcharhost:{token}:catbox")', addchar_source)
        self.assertIn("upload_to_catbox", addchar_source)
        self.assertIn("chat_id=CHARA_CHANNEL_ID", addchar_source)

        update_source = (ROOT / "waifu/aoiwaifu/admin/update.py").read_text(encoding="utf-8")
        self.assertIn('filters.command(["gdelete", "deletechar"])', update_source)
        self.assertIn('filters.command(["gupdate", "update"])', update_source)
        self.assertIn('filters.command(["add"])', source)
        self.assertFalse((ROOT / "waifu/aoiwaifu/admin/reupload.py").exists())
        self.assertNotIn("/reupload", (ROOT / "waifu/aoiwaifu/unit/aoi_help.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
