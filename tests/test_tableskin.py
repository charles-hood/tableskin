"""Unit tests for tableskin.py. Run: ./.venv/bin/python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tableskin as ts  # noqa: E402

SAMPLES = ROOT / "samples"


class Numbers(unittest.TestCase):
    def test_lenient_grammar(self):
        cases = {
            "1200": 1200, "-45.50": -45.5, "1,200.00": 1200, "$1,200.00": 1200, "-$5": -5, "$-5": -5,
            "+7": 7, "12%": 12, "32G": 32, "(45.50)": -45.5, "0": 0, "0.5": 0.5, "−12": -12,
            "1 200": 1200, "95.0": 95,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ts.parse_number(text)[0], want)

    def test_text_stays_text(self):
        for text in ["007", "02134", "1e6", ".5", "1200,50", "TX-4060", "B07", "36139dd", "$12$", "(+5)",
                     "2026-10-04", "08:15", "", "abc", "1,20"]:
            with self.subTest(text=text):
                self.assertIsNone(ts.parse_number(text))

    def test_currency_and_percent_flags(self):
        self.assertEqual(ts.parse_number("$3")[1:], (True, False))
        self.assertEqual(ts.parse_number("3%")[1:], (False, True))
        self.assertEqual(ts.parse_number("3 USD")[1:], (True, False))


class Roles(unittest.TestCase):
    def roles(self, name):
        return {c["name"]: c["role"] for c in ts.analyze(*ts.load(SAMPLES / name))["columns"]}

    def test_sample_roles(self):
        self.assertEqual(self.roles("transactions.csv"), {
            "date": "date", "id": "id", "description": "text", "category": "label",
            "amount": "money", "balance": "money"})
        self.assertEqual(self.roles("ports.csv"), {
            "switch": "label", "port": "ordinal", "speed": "number", "state": "status",
            "tx util %": "percent", "rx util %": "percent", "crc errors": "number"})
        self.assertEqual(self.roles("sprint.csv")["status"], "status")
        self.assertEqual(self.roles("chat.csv")["sender"], "person")

    def test_picks(self):
        want = {"transactions.csv": ["ledger"], "invoice.csv": ["paper"], "departures.csv": ["splitflap"],
                "sprint.csv": ["board"], "chat.csv": ["chat"], "ports.csv": ["clean", "heat"],
                "cities.csv": ["clean", "bars"]}
        for name, skin in want.items():
            with self.subTest(name=name):
                self.assertEqual(ts.pick(ts.analyze(*ts.load(SAMPLES / name)))[0], skin)

    def test_lanes_run_in_tone_order(self):
        model = ts.analyze(*ts.load(SAMPLES / "sprint.csv"))
        self.assertEqual(model["groups"], ["To Do", "In Progress", "In Review", "Done"])

    def test_inputs(self):
        records = [{"a": 1, "b": None}, {"a": 2, "c": "x"}]
        self.assertEqual(ts.load(records), (["a", "b", "c"], [["1", "", ""], ["2", "", "x"]]))
        self.assertEqual(ts.load([["h1", "h2"], [1, 2.5]]), (["h1", "h2"], [["1", "2.5"]]))
        self.assertEqual(ts.load("a;b\n1;2\n"), (["a", "b"], [["1", "2"]]))


class Markup(unittest.TestCase):
    def test_cells_are_text_not_html(self):
        html = ts.render(ts.analyze(['x"<y>'], [["<script>alert(1)</script>"], ["a & b"]]), "clean")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn('data-col="x&quot;&lt;y&gt;"', html)
        self.assertIn("a &amp; b", html)

    def test_hooks(self):
        html = ts.render(ts.analyze(*ts.load(SAMPLES / "transactions.csv")), "ledger")
        self.assertIn('<tr data-row="2" data-key="TX-4060" data-run="start" data-group="dining" data-group-start', html)
        self.assertIn('class="number negative" data-signed style="--j:4;--t:0.267;--mag:0.008"', html)
        self.assertIn('data-tag="dining" style="--j:3;--hue:210"', html)

    def test_total_rows(self):
        html = ts.render(ts.analyze(*ts.load(SAMPLES / "invoice.csv")))
        self.assertEqual(html.count(" data-total"), 3)

    def test_chat_keys_on_person_and_me(self):
        html = ts.render(ts.analyze(*ts.load(SAMPLES / "chat.csv")), "chat", me="Sam")
        self.assertIn('data-key="Sam" data-me data-run="start"', html)
        self.assertIn('data-key="Ana" style', html)  # second Ana message continues the run

    def test_unknown_skin_and_key(self):
        model = ts.analyze(["a"], [["1"]])
        with self.assertRaises(ValueError):
            ts.css("nope")
        with self.assertRaises(ValueError):
            ts.render(model, "clean", key="missing")

    def test_page_is_standalone(self):
        doc = ts.page(SAMPLES / "cities.csv", title="Cities")
        self.assertTrue(doc.startswith("<!doctype html>"))
        self.assertIn("@layer tableskin.base", doc)
        self.assertIn('data-skin="clean bars"', doc)
        self.assertIn("<caption>Cities</caption>", doc)


class Files(unittest.TestCase):
    def test_bundle_is_current(self):
        self.assertEqual((ROOT / "tableskin.css").read_text(encoding="utf-8"), ts.bundle(),
                         "tableskin.css is stale: run tableskin.py --bundle")

    def test_every_skin_is_scoped(self):
        for name in ts.SKINS + ts.MODIFIERS:
            text = (ts.SKIN_DIR / ("%s.css" % name)).read_text(encoding="utf-8")
            with self.subTest(skin=name):
                self.assertIn('[data-skin~="%s"]' % name, text)
                self.assertIn("@layer tableskin.", text)


if __name__ == "__main__":
    unittest.main()
