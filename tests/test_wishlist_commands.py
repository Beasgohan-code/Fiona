import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIFU = ROOT / "waifu/aoiwaifu"
WISHLIST = WAIFU / "modules/wishlist.py"


def _load_helpers():
    tree = ast.parse(WISHLIST.read_text(encoding="utf-8"))
    names = {"_canonical_id", "_id_candidates", "_normalise_wishlist", "_wishlist_update_filter"}
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(WISHLIST), "exec"), namespace)
    return namespace


class WishlistCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_helpers()

    def test_id_helpers_match_legacy_numeric_and_zero_padded_ids(self):
        self.assertEqual(self.helpers["_canonical_id"]("0007"), "7")
        self.assertEqual(self.helpers["_id_candidates"]("07"), ["07", 7])

    def test_wishlist_normalizes_duplicate_ids_and_rejects_corrupt_values(self):
        normalize = self.helpers["_normalise_wishlist"]
        self.assertEqual(normalize(["007", 7, "12"]), ["7", "12"])
        self.assertEqual(normalize(None), [])
        self.assertIsNone(normalize(["7", {"bad": "entry"}]))

    def test_update_filter_uses_compare_and_set_for_existing_or_new_field(self):
        update_filter = self.helpers["_wishlist_update_filter"]
        user = {"_id": "user-doc", "wishlist": ["2", "5"]}
        query = update_filter(user)
        self.assertEqual(query["_id"], "user-doc")
        self.assertEqual(query["$or"], [
            {"wishlist": {"$exists": False}},
            {"wishlist": ["2", "5"]},
        ])
        self.assertEqual(update_filter({"_id": "new-user"})["$or"], [{"wishlist": {"$exists": False}}])

    def test_commands_are_registered_and_documented(self):
        source = WISHLIST.read_text(encoding="utf-8")
        self.assertIn('filters.command(["wishlist", "wish"])', source)
        self.assertIn('filters.command("unwish")', source)
        self.assertIn("_MAX_WISHLIST = 20", source)
        help_source = (WAIFU / "unit/aoi_help.py").read_text(encoding="utf-8")
        self.assertIn("/wishlist [id]", help_source)
        self.assertIn("/unwish <id>", help_source)
        menu_source = (ROOT / "unified_commands.py").read_text(encoding="utf-8")
        self.assertIn('(\"wishlist\", \"View or add to your character wishlist\")', menu_source)
        self.assertIn('(\"unwish\", \"Remove a character from your wishlist\")', menu_source)


if __name__ == "__main__":
    unittest.main()
