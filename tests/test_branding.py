import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def string_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_values(item)
    elif isinstance(value, str):
        yield value


class BrandingTests(unittest.TestCase):
    def test_waifu_ui_strings_use_fiona_branding(self):
        locale_dir = ROOT / "waifu/aoiwaifu/langs"
        for locale_file in locale_dir.glob("*.json"):
            with self.subTest(locale=locale_file.name):
                data = json.loads(locale_file.read_text(encoding="utf-8"))
                visible_strings = "\n".join(string_values(data)).casefold()
                for legacy_brand in ("aoi network", "aoinetwork", "aoiwaifubot", "aoi waifu", "aoiwaifu"):
                    self.assertNotIn(legacy_brand, visible_strings)

    def test_required_music_mit_notice_is_preserved(self):
        notice = (ROOT / "licenses/AoiMusic-MIT.txt").read_text(encoding="utf-8")
        self.assertIn("MIT License", notice)
        self.assertIn("Copyright (c)", notice)
        self.assertIn("permission notice shall be included", notice)


if __name__ == "__main__":
    unittest.main()
