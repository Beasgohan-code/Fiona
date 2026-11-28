"""tr_panel() must translate the text fragments of a trusted HTML panel
without ever touching its markup, and the panel call sites must use it."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIFU = ROOT / "waifu/aoiwaifu"
AOI_LANG = WAIFU / "unit/aoi_lang.py"


def _load_tr_panel():
    tree = ast.parse(AOI_LANG.read_text(encoding="utf-8"))
    node = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "tr_panel"
    )
    namespace = {
        # Stub the dependencies so the pure panel walker runs in isolation.
        "tr": lambda text, lang="en": f"<{text}|{lang}>",
        "normalize_lang_code": lambda lang: lang,
        "DEFAULT_LANG": "en",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(AOI_LANG), "exec"), namespace)
    return namespace["tr_panel"]


class TrPanelBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tr_panel = _load_tr_panel()

    def test_tags_and_attributes_are_never_translated(self):
        panel = '<b>Name:</b> <a href="https://t.me/u/1">Goku</a> <code>07</code>'
        out = self.tr_panel(panel, "es")
        self.assertIn("<b>", out)
        self.assertIn("</b>", out)
        self.assertIn('href="https://t.me/u/1"', out)
        self.assertIn("<07|es>", out)  # tag contents untouched, text translated

    def test_text_fragments_are_translated_between_tags(self):
        out = self.tr_panel("<b>Name:</b> Goku", "es")
        self.assertEqual(out, "<b><Name:|es></b>< Goku|es>")

    def test_nested_tags_keep_nesting(self):
        out = self.tr_panel("<blockquote><b>Hi</b></blockquote>", "es")
        self.assertEqual(out, "<blockquote><b><Hi|es></b></blockquote>")

    def test_default_lang_returns_panel_unchanged(self):
        panel = "<b>Name:</b> Goku & <i>Friends</i>"
        self.assertEqual(self.tr_panel(panel, "en"), panel)

    def test_empty_and_non_string_input(self):
        self.assertEqual(self.tr_panel("", "es"), "")
        self.assertEqual(self.tr_panel(None, "es"), "None")


class PanelCallSiteTests(unittest.TestCase):
    def test_no_trusted_html_panel_is_fed_to_plain_tr(self):
        pattern = re.compile(r"\btr\((?:rich_card|rich_showcase_panel|notice_card|premium_text)\(")
        offenders = [
            str(path)
            for path in WAIFU.rglob("*.py")
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], offenders)

    def test_shop_panel_failure_path_uses_tr_panel(self):
        src = (WAIFU / "modules/shop.py").read_text(encoding="utf-8")
        self.assertIn("tr_panel(f'{caption}", src)
        self.assertNotIn("tr(f'{caption}", src)


if __name__ == "__main__":
    unittest.main()
