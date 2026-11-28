import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MusicPlayerCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Pillow is an application dependency and is not installed")

        py_yt = types.ModuleType("py_yt")
        py_yt.VideosSearch = object
        httpx = types.ModuleType("httpx")
        httpx.AsyncClient = object
        aoi = types.ModuleType("AoiMusic")
        aoi.__path__ = []
        utils = types.ModuleType("AoiMusic.utils")
        utils.__path__ = []
        rich_msg = types.ModuleType("AoiMusic.utils.rich_msg")
        rich_msg.url_ok = None
        cls._stubs = {
            "httpx": httpx,
            "py_yt": py_yt,
            "AoiMusic": aoi,
            "AoiMusic.utils": utils,
            "AoiMusic.utils.rich_msg": rich_msg,
        }
        module_path = ROOT / "music/AoiMusic/utils/thumbnails.py"
        spec = importlib.util.spec_from_file_location("fiona_music_thumbnails_test", module_path)
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, cls._stubs):
            spec.loader.exec_module(cls.module)

    def test_asset_paths_resolve_to_bundled_music_assets(self):
        self.assertTrue(self.module._BASE_IMG.is_file())
        self.assertTrue(self.module._FONT_BOLD.is_file())
        self.assertTrue(self.module._FONT_REG.is_file())

    def test_rendered_card_uses_cover_art_and_is_telegram_sized(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            cover = Path(tmp) / "cover.jpg"
            output = Path(tmp) / "player.png"
            Image.new("RGB", (480, 320), "#c53991").save(cover)
            result = self.module._render_pillow_card(
                "A long title for an atmospheric player card",
                "Fiona Artist",
                "03:42",
                "Requested by Fiona",
                cover,
                None,
                output,
                "01:12",
            )
            with Image.open(result) as card:
                self.assertEqual(card.size, (1280, 720))
                self.assertEqual(card.format, "PNG")
                self.assertGreater(len(card.getcolors(maxcolors=1_000_000) or []), 100)

    def test_missing_cover_still_produces_original_abstract_art(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "player.png"
            result = self.module._render_pillow_card(
                "Track without artwork", "Fiona", "Live", "Listener", None, None, output
            )
            with Image.open(result) as card:
                self.assertEqual(card.size, (1280, 720))
                self.assertEqual(card.format, "PNG")


if __name__ == "__main__":
    unittest.main()
