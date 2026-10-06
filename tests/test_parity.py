"""tableskin.js must write exactly what tableskin.py writes.

Two checks: the string renderer under Node for every sample and fixture, and
skinTable() on a plain table in headless Chrome against the Python markup.
Each skips when its tool (node, Chrome) is missing.
"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tableskin as ts  # noqa: E402

CASES = [{"path": str(p)} for p in sorted((ROOT / "samples").glob("*.csv"))]
CASES += [{"path": str(p)} for p in sorted((ROOT / "tests" / "fixtures").glob("*.csv"))]
CASES += [
    {"path": str(ROOT / "samples" / "chat.csv"), "skin": "chat", "me": "Sam", "title": "Hike <&>"},
    {"path": str(ROOT / "samples" / "ports.csv"), "skin": "ledger bars", "key": "switch"},
    {"path": str(ROOT / "samples" / "transactions.csv"), "skin": "board"},
]
CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome"), shutil.which("chromium")] if p and Path(p).exists()), None)


def python_side(case):
    model = ts.analyze(*ts.load(Path(case["path"])))
    return {"pick": list(ts.pick(model)), "roles": [c["role"] for c in model["columns"]],
            "html": ts.render(model, case.get("skin", "auto"), case.get("title"), case.get("key"), case.get("me"))}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class NodeParity(unittest.TestCase):
    def test_same_markup(self):
        out = subprocess.run(["node", str(ROOT / "tests" / "parity.mjs"), json.dumps(CASES)],
                             capture_output=True, text=True, check=True).stdout
        for case, js in zip(CASES, json.loads(out)):
            py = python_side(case)
            with self.subTest(case=Path(case["path"]).name, skin=case.get("skin", "auto")):
                self.assertEqual(js["roles"], py["roles"])
                self.assertEqual(js["pick"], py["pick"])
                self.assertEqual(js["html"], py["html"])


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(CHROME, "Chrome not found")
class DomParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(_Quiet, directory=str(ROOT))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def skinned(self, csv, skin, title):
        q = urllib.parse.urlencode({"csv": "../" + csv, "skin": skin, "title": title})
        url = "http://127.0.0.1:%d/tests/dom.html?%s" % (self.server.server_port, q)
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=5000",
                              "--dump-dom", url], capture_output=True, text=True, timeout=60).stdout
        m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(m, "the page did not finish: " + dom[-400:])
        text = m.group(1)
        for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&amp;", "&")):
            text = text.replace(a, b)
        return text

    def test_skin_table_in_place(self):
        for csv, skin in (("samples/transactions.csv", "ledger"), ("samples/ports.csv", "auto"),
                          ("tests/fixtures/status.csv", "auto")):
            with self.subTest(csv=csv):
                got = self.skinned(csv, skin, "T")
                model = ts.analyze(*ts.load(ROOT / csv))
                want = ts.render(model, skin, "T")
                # The DOM writes flags as name="" and escapes text its own way.
                got = got.replace('=""', "")
                want = want.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
                self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
