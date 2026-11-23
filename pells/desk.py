"""The desk: a large-type window in the browser, served from this computer.

    pells desk [--port 8780] [--work DIR] [--no-open]

Starts a Python http.server on 127.0.0.1 and opens /desk/index.html. The buttons call the same
engine as the command line through small JSON endpoints. Each API call carries a token printed
into the page at start-up, and the server answers requests addressed to 127.0.0.1 or localhost.
"""
import csv
import json
import os
import secrets
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import chats, ledger, piles, produce, receipts, searchlog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "desk")
EXAMPLE = os.path.join(ROOT, "examples", "doe-v-roe")
TYPES = {".html": "text/html; charset=utf-8", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".json": "application/json"}
MAX_UPLOAD = 60 * 1024 * 1024
QUIET = lambda *_a: None  # noqa: E731


class State(object):
    token = ""
    work = ""


def safe_name(name):
    name = os.path.basename(urllib.parse.unquote(name or "file.pdf"))
    keep = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in name).strip(" .")
    return keep or "file.pdf"


def state():
    """What the page shows: the index, the piles with their marks, the productions, the log."""
    work = State.work
    out = {"work": work, "has_ledger": False, "statements": [], "gaps": [], "not_read": [], "unread_pages": [],
           "piles": [], "productions": [], "log": searchlog.render(work) if os.path.isdir(work) else "",
           "example": os.path.isdir(EXAMPLE)}
    if not os.path.exists(os.path.join(work, "ledger.json")):
        return out
    led = ledger.load(work)
    out["has_ledger"] = True
    out["folder"] = led["folder"]
    out["totals"] = {"files": len(led["files"]), "pages": sum(f["pages"] for f in led["files"]),
                     "statements": len(led["statements"]), "lines": len(led["rows"]), "repeat_pages": led["repeat_pages"]}
    for s in sorted(led["statements"], key=lambda s: (str(s["acct"]), str(s["start"]))):
        out["statements"].append({"acct": ledger.mask(s["acct"]), "start": s["start"], "end": s["end"], "lines": s["lines"],
                                  "begin": ledger.money(s["begin"]), "close": ledger.money(s["close"]), "check": s["check"]})
    out["gaps"] = [dict(g, acct=ledger.mask(g["acct"])) for g in ledger.gaps(led["statements"])]
    out["not_read"] = [f for f in led["files"] if f["status"] != "read"]
    out["unread_pages"] = led["unread_pages"]
    mp = os.path.join(work, "marks.csv")
    if os.path.exists(mp):
        order, by = [], {}
        with open(mp, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["pile"] not in by:
                    by[r["pile"]] = []
                    order.append(r["pile"])
                by[r["pile"]].append({"id": r["id"], "mark": r["produce"], "date": r["date"], "acct": r["account"],
                                      "debit": r["debit"], "credit": r["credit"], "desc": r["description"],
                                      "file": r["file"], "page": r["page"]})
        out["piles"] = [{"pile": name, "lines": by[name]} for name in order]
    for d in sorted(os.listdir(work)):
        pj = os.path.join(work, d, "production.json")
        if d.startswith("production-") and os.path.exists(pj):
            with open(pj, encoding="utf-8") as fh:
                data = json.load(fh)
            out["productions"].append({"range": "%s%0*d to %s" % (data["prefix"], len(data["last"]) - len(data["prefix"]), data["start"], data["last"]),
                                       "next": data["next"], "index": "%s/production-index.txt" % d,
                                       "files": ["%s/%s" % (d, f["output"]) for f in data["files"]]})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "PellsDesk/0.1"

    def log_message(self, fmt, *args):
        pass

    def _host_ok(self):
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _token_ok(self, q):
        t = self.headers.get("X-Pells-Token") or (q.get("t") or [""])[0]
        return secrets.compare_digest(t, State.token)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "host"})
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/desk", "/desk/"):
            self.send_response(302)
            self.send_header("Location", "/desk/index.html")
            self.end_headers()
            return
        if u.path == "/desk/index.html":
            with open(os.path.join(STATIC, "index.html"), "rb") as fh:
                body = fh.read().replace(b"{{TOKEN}}", State.token.encode())
            return self._send(200, body, TYPES[".html"])
        if not self._token_ok(q):
            return self._send(403, {"error": "token"})
        if u.path == "/api/state":
            return self._send(200, state())
        if u.path == "/files":
            rel = (q.get("path") or [""])[0]
            real = os.path.realpath(os.path.join(State.work, rel))
            base = os.path.realpath(State.work)
            if not real.startswith(base + os.sep) or not os.path.isfile(real):
                return self._send(404, {"error": "not found"})
            with open(real, "rb") as fh:
                body = fh.read()
            ext = os.path.splitext(real)[1].lower()
            disp = "inline" if ext in (".pdf", ".txt") else "attachment"
            return self._send(200, body, TYPES.get(ext, "application/octet-stream"),
                              {"Content-Disposition": '%s; filename="%s"' % (disp, os.path.basename(real))})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "host"})
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._token_ok(q):
            return self._send(403, {"error": "token"})
        work = State.work
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_UPLOAD:
                return self._send(413, {"error": "file over 60 MB"})
            if u.path == "/api/upload":
                up = os.path.join(work, "uploads")
                os.makedirs(up, exist_ok=True)
                name = safe_name((q.get("name") or [""])[0])
                with open(os.path.join(up, name), "wb") as fh:
                    fh.write(self.rfile.read(n))
                return self._send(200, {"name": name, "folder": up})
            data = json.loads((self.rfile.read(n) if n else b"{}").decode("utf-8") or "{}")
            if u.path == "/api/read":
                folder = data.get("folder") or ""
                if data.get("example"):
                    folder = os.path.join(EXAMPLE, "statements")
                elif data.get("uploads"):
                    folder = os.path.join(work, "uploads")
                folder = os.path.expanduser(folder.strip())
                if not folder or not os.path.exists(folder):
                    return self._send(400, {"error": "no such folder: %s" % (folder or "(empty)")})
                ledger.read(folder, work, log=QUIET)
                piles.build(work, log=QUIET)
                return self._send(200, state())
            if u.path == "/api/mark":
                piles.set_mark(work, set(data.get("ids") or []), data.get("value") or "")
                return self._send(200, {"ok": True})
            if u.path == "/api/produce":
                res = produce.produce(work, data.get("prefix") or "DOC", int(data.get("start") or 1),
                                      data.get("unit") or "page", bool(data.get("first_page")), 6,
                                      bool(data.get("replace")), log=QUIET)
                return self._send(200, {"text": res["text"], "state": state()})
            if u.path in ("/api/receipts", "/api/chats"):
                kind = u.path.rsplit("/", 1)[1]
                folder = os.path.join(EXAMPLE, kind) if data.get("example") else os.path.expanduser((data.get("folder") or "").strip())
                if not folder or not os.path.isdir(folder):
                    return self._send(400, {"error": "no such folder: %s" % (folder or "(empty)")})
                if kind == "receipts":
                    receipts.pair(folder, work, log=QUIET)
                else:
                    chats.search(folder, work, log=QUIET)
                with open(os.path.join(work, kind + ".txt"), encoding="utf-8") as fh:
                    return self._send(200, {"text": fh.read(), "log": searchlog.render(work)})
        except SystemExit as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            return self._send(500, {"error": "%s: %s" % (type(exc).__name__, exc)})
        return self._send(404, {"error": "not found"})


def serve(port=8780, work="pells-work", open_browser=True):
    State.token = secrets.token_urlsafe(18)
    State.work = os.path.abspath(work)
    os.makedirs(State.work, exist_ok=True)
    try:
        os.getcwd()
    except OSError:
        # started from a folder macOS will not let this process read (Desktop, Documents); reportlab asks for the current folder
        os.chdir(State.work)
    httpd = None
    for p in range(port, port + 10):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            print("port %d is in use; trying %d" % (p, p + 1))
    if httpd is None:
        print("no free port between %d and %d; pass --port" % (port, port + 9))
        return 1
    url = "http://127.0.0.1:%d/desk/index.html" % httpd.server_address[1]
    print("Pells desk: %s" % url, flush=True)
    print("Work folder: %s" % State.work)
    print("Press Control-C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
