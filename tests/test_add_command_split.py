"""Fiona has a single /add command shared by two features:

- the economy admin action:    /add c|b <amount> [target]
- the character admin action:  /add <name> <anime> <rarity-id> <url>

Both used to register on plain filters.command("add"), so every invocation got
two replies (and whichever handler ran second saw a mangled shape). The three
predicates below are the disjoint partition; keep it that way.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD = ROOT / "waifu/aoiwaifu/admin/upload.py"
ECONOMY = ROOT / "waifu/aoiwaifu/admin/economy.py"


def _extract(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == names, f"missing {names - {n.name for n in nodes}} in {path}"
    return {node.name: node for node in nodes}


def _load_predicates():
    nodes = {}
    nodes.update(_extract(UPLOAD, {"_is_character_add"}))
    nodes.update(_extract(ECONOMY, {"_is_currency_add", "_is_other_add"}))
    namespace = {}
    exec(
        compile(ast.Module(body=list(nodes.values()), type_ignores=[]), str(UPLOAD), "exec"),
        namespace,
    )
    return namespace


class FakeMessage:
    def __init__(self, command):
        self.command = command


SAMPLES = [
    ["add"],
    ["add", "c"],
    ["add", "c", "100"],
    ["add", "C", "100"],
    ["add", "b", "5000", "123456789"],
    ["add", "b", "@someone"],
    ["add", "name", "anime", "16", "https://i.ibb.co/x.png"],
    ["add", "name", "anime", "x", "https://i.ibb.co/x.png"],
    ["add", "name", "anime", "16"],
    ["add", "c", "5", "6", "https://i.ibb.co/x.png"],
    ["add", "foo", "bar"],
    ["add", "1", "2", "3", "4"],
]


class AddCommandPartitionTests(unittest.TestCase):
    def setUp(self):
        self.p = _load_predicates()

    def _eval(self, name, command):
        return bool(self.p[name](None, None, FakeMessage(command)))

    def test_currency_and_character_forms_are_disjoint(self):
        for command in SAMPLES:
            currency = self._eval("_is_currency_add", command)
            character = self._eval("_is_character_add", command)
            self.assertFalse(
                currency and character, f"both handlers would fire for {command}"
            )

    def test_other_add_is_exactly_the_complement(self):
        for command in SAMPLES:
            currency = self._eval("_is_currency_add", command)
            character = self._eval("_is_character_add", command)
            other = self._eval("_is_other_add", command)
            self.assertEqual(other, not (currency or character), command)

    def test_character_form_requires_numeric_rarity(self):
        self.assertTrue(self._eval("_is_character_add", ["add", "x", "y", "7", "https://u"]))
        self.assertFalse(self._eval("_is_character_add", ["add", "x", "y", "seven", "https://u"]))

    def test_currency_form_wins_the_c_b_prefix(self):
        command = ["add", "c", "5", "6", "https://i.ibb.co/x.png"]
        self.assertTrue(self._eval("_is_currency_add", command))
        self.assertFalse(self._eval("_is_character_add", command))
        self.assertFalse(self._eval("_is_other_add", command))

    def test_source_wiring_uses_the_predicates(self):
        upload_src = UPLOAD.read_text(encoding="utf-8")
        economy_src = ECONOMY.read_text(encoding="utf-8")
        self.assertIn('filters.command(["add"]) & filters.create(_is_character_add)', upload_src)
        self.assertIn('filters.command("add") & filters.create(_is_currency_add)', economy_src)
        self.assertIn('filters.command("add") & filters.create(_is_other_add)', economy_src)


if __name__ == "__main__":
    unittest.main()
