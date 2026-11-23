"""The desk's JSON endpoints, called over HTTP on a port the system picks."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import make_example  # noqa: E402
from pells import desk  # noqa: E402


def test_desk_endpoints(tmp_path):
    ex = os.path.join(str(tmp_path), "ex")
    make_example.main([ex], quiet=True)
    desk.State.token = "t0ken"
    desk.State.work = os.path.join(str(tmp_path), "work")
    os.makedirs(desk.State.work)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), desk.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def call(path, body=None, token="t0ken", raw=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(base + path, data=data, headers={"X-Pells-Token": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        code, page = call("/desk/index.html")
        assert code == 200 and b"t0ken" in page and b"Pells" in page
        assert call("/api/state", token="wrong")[0] == 403
        code, body = call("/api/state")
        assert code == 200 and json.loads(body)["has_ledger"] is False
        assert call("/api/read", {"folder": os.path.join(ex, "nowhere")})[0] == 400
        code, body = call("/api/read", {"folder": os.path.join(ex, "statements")})
        s = json.loads(body)
        assert code == 200 and s["totals"]["lines"] == 26 and len(s["statements"]) == 4
        assert [x["check"] for x in s["statements"]].count("reconciled") == 3
        assert "000111222333" not in body.decode("utf-8").replace(s["folder"], "")
        trades = [p for p in s["piles"] if p["pile"].startswith("Building trades")][0]
        assert call("/api/mark", {"ids": [x["id"] for x in trades["lines"]], "value": "y"})[0] == 200
        code, body = call("/api/produce", {"prefix": "DOE", "start": 1, "unit": "page"})
        j = json.loads(body)
        assert code == 200 and "Next number: DOE" in j["text"] and len(j["state"]["productions"]) == 1
        assert call("/api/produce", {"prefix": "DOE", "start": 1})[0] == 400          # a second one needs replace
        rel = j["state"]["productions"][0]["files"][0]
        code, pdf = call("/files?path=" + urllib.request.quote(rel))
        assert code == 200 and pdf[:4] == b"%PDF"
        assert call("/files?path=" + urllib.request.quote("../ex/statements/document (2).pdf"))[0] == 404
        code, body = call("/api/receipts", {"folder": os.path.join(ex, "receipts")})
        assert code == 200 and "3 paired" in json.loads(body)["text"]
        code, body = call("/api/chats", {"folder": os.path.join(ex, "chats")})
        assert code == 200 and "3 threads read" in json.loads(body)["text"]
        code, body = call("/api/upload?name=" + urllib.request.quote("../../evil name.pdf"), raw=b"%PDF-1.4 not a statement")
        assert code == 200 and json.loads(body)["name"] == "evil name.pdf"
        assert os.path.exists(os.path.join(desk.State.work, "uploads", "evil name.pdf"))
    finally:
        httpd.shutdown()
        httpd.server_close()
