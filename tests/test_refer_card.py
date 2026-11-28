import json
import string
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGS = ROOT / "waifu" / "aoiwaifu" / "langs"
REFERRAL_SRC = ROOT / "waifu" / "aoiwaifu" / "modules" / "referral.py"

# Exact kwargs the referral card code is expected to pass to t('refer_caption').
EXPECTED_KWARGS = {
    "ref_dollars": 25,
    "ref_coins": 1000,
    "referrals_count": 0,
    "char_milestone_status": "🌟 0 Referrals",
    "total_dollars": 0,
    "total_coins": 0,
    "history_block": "  <i>none</i>",
    "ref_link": "https://t.me/FionaBot?start=ref_1",
}


class ReferCaptionTests(unittest.TestCase):
    def test_all_language_files_format_refer_caption(self):
        lang_files = sorted(LANGS.glob("*.json"))
        self.assertTrue(lang_files, "no language files found")
        for path in lang_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            template = data.get("refer_caption")
            self.assertIsInstance(template, str, f"{path.name} missing refer_caption")
            fields = {
                field.split(".")[0].split("[")[0]
                for _, field, _, _ in string.Formatter().parse(template)
                if field
            }
            missing = fields - set(EXPECTED_KWARGS)
            self.assertFalse(
                missing,
                f"{path.name}: refer_caption uses kwargs the code does not provide: {sorted(missing)}",
            )
            rendered = template.format(**EXPECTED_KWARGS)
            self.assertNotIn("{", rendered, f"{path.name}: unfilled placeholder left in refer_caption")

    def test_referral_call_site_passes_computed_kwargs(self):
        src = REFERRAL_SRC.read_text(encoding="utf-8")
        for kwarg in (
            "total_dollars=total_dollars",
            "total_coins=total_coins",
            "history_block=history_block",
        ):
            self.assertIn(
                kwarg,
                src,
                f"referral card no longer passes {kwarg} — the raw template would be shown to users",
            )


if __name__ == "__main__":
    unittest.main()
