import ast
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ImageAssetTests(unittest.TestCase):
    def test_generated_assets_are_bundled_and_small_enough_for_telegram(self):
        assets = (
            ROOT / "music/assets/fiona_start_ping.jpg",
            ROOT / "waifu/assets/fiona_collection.jpg",
            ROOT / "waifu/assets/fiona_shop.jpg",
        )
        for asset in assets:
            with self.subTest(asset=asset.name):
                self.assertTrue(asset.is_file())
                self.assertGreater(asset.stat().st_size, 30_000)
                self.assertLess(asset.stat().st_size, 10 * 1024 * 1024)
                self.assertEqual(asset.read_bytes()[:2], b"\xff\xd8")

    def test_start_ping_and_waifu_static_fallbacks_use_bundled_assets(self):
        music_config = (ROOT / "music/config/config.py").read_text(encoding="utf-8")
        waifu_config = (ROOT / "waifu/aoiwaifu/config.py").read_text(encoding="utf-8")
        ping = (ROOT / "music/AoiMusic/plugins/tools/ping.py").read_text(encoding="utf-8")
        rank = (ROOT / "waifu/aoiwaifu/modules/rank.py").read_text(encoding="utf-8")
        shop = (ROOT / "waifu/aoiwaifu/modules/shop.py").read_text(encoding="utf-8")
        self.assertIn('"fiona_start_ping.jpg"', music_config)
        self.assertIn("PING_IMG_URL", ping)
        self.assertIn('"fiona_start_ping.jpg"', waifu_config)
        self.assertIn('"fiona_collection.jpg"', waifu_config)
        self.assertIn('"fiona_shop.jpg"', waifu_config)
        self.assertIn("from aoiwaifu import PHOTO_URL", rank)
        self.assertIn("SHOP_IMAGE_URL = WAIFU_SHOP_IMAGE", shop)

    def test_start_media_picker_shuffles_without_repeating_until_cycle_finishes(self):
        start_path = ROOT / "waifu/aoiwaifu/modules/start.py"
        tree = ast.parse(start_path.read_text(encoding="utf-8"))
        picker = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "pick_start_media"
        )
        namespace = {
            "START_MEDIA": ["one.jpg", "two.jpg", "three.jpg"],
            "_start_media_cycle": [],
            "random": random,
        }
        exec(compile(ast.Module(body=[picker], type_ignores=[]), str(start_path), "exec"), namespace)
        first_cycle = [namespace["pick_start_media"]() for _ in range(3)]
        self.assertEqual(set(first_cycle), {"one.jpg", "two.jpg", "three.jpg"})
        self.assertIn(namespace["pick_start_media"](), first_cycle)

    def test_waifu_start_media_defaults_to_a_randomized_local_rotation(self):
        config = (ROOT / "waifu/aoiwaifu/config.py").read_text(encoding="utf-8")
        start = (ROOT / "waifu/aoiwaifu/modules/start.py").read_text(encoding="utf-8")
        self.assertIn('[os.getenv("PHOTO_URL_1", "").strip() or WAIFU_START_IMAGE, WAIFU_COLLECTION_IMAGE]', config)
        self.assertGreaterEqual(start.count("pick_start_media()"), 3)


if __name__ == "__main__":
    unittest.main()
