"""Statements in, ledger out.

    read(folder, work) reads the PDFs page by page, files each transaction under the account
    and period printed on its own page, and checks each statement's lines against its printed
    opening and closing balance.

Written to the work folder: ledger.json, ledger.csv, index.txt, and a line in the search log.
"""
import csv
import hashlib
import json
import os
import re
from datetime import date, timedelta

from . import layouts as lay
from . import pages as pg
from . import searchlog

CENT = 0.005


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def _iso(d):
    return d.isoformat() if d else None


def _rel(path, root):
    try:
        return os.path.relpath(path, root if os.path.isdir(root) else os.path.dirname(root))
    except ValueError:
        return path


def read(folder, work, extra_layouts=None, log=print):
    folder = os.path.abspath(os.path.expanduser(folder))
    os.makedirs(work, exist_ok=True)
    L = lay.load([extra_layouts, os.path.join(work, "layouts")])
    files, stmts, order, unread = [], {}, [], []
    seen_sha, seen_page, repeats = {}, set(), 0

    for path in pg.list_pdfs(folder):
        rel = _rel(path, folder)
        sha, texts = pg.read_pages(path, os.path.join(work, "_pagetext"))
        rec = {"file": rel, "sha256": sha, "pages": len(texts or []), "status": "read", "copy_of": None}
        files.append(rec)
        if sha in seen_sha:
            rec["status"], rec["copy_of"] = "same file as an earlier one", seen_sha[sha]
            continue
        seen_sha[sha] = rel
        if texts is None:
            rec["status"] = "did not open as a PDF"
            continue
        if not pg.has_text(texts):
            rec["status"] = "no text layer (a scan); run OCR first"
            continue

        # a layout and a header for each page
        cur, last_head, plan = None, None, []
        for i, text in enumerate(texts):
            found = lay.pick(L, text)
            use = found or (cur if cur is not None and cur.get("carry") else None)
            if use is None:
                n = len(lay.MONEYISH.findall(text))
                if n >= 3:
                    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                    unread.append({"file": rel, "page": i + 1, "amounts_on_page": n, "first_line": first[:70]})
                plan.append(None)
                continue
            if found is not None and found is not cur:
                last_head = None
            cur = use
            h = lay.header(use, text)
            if use.get("carry") and last_head:
                for k in ("acct", "start", "end"):
                    if h[k] is None:
                        h[k] = last_head[k]
            if h["acct"] or h["end"]:
                last_head = dict(h)
            plan.append((use, h))

        # consecutive pages of one layout are read as one run
        i = 0
        while i < len(plan):
            if plan[i] is None:
                i += 1
                continue
            use = plan[i][0]
            j = i
            while j < len(plan) and plan[j] is not None and plan[j][0] is use:
                j += 1
            run = []
            for k in range(i, j):
                h = plan[k][1]
                sig = (h["acct"], _iso(h["start"]), _iso(h["end"]), hashlib.sha1(_norm(texts[k]).encode("utf-8")).hexdigest())
                if sig in seen_page:
                    repeats += 1           # the same page again, in a bundle or a second download
                    continue
                seen_page.add(sig)
                run.append((k, texts[k]))
                key = (h["acct"], _iso(h["start"]), _iso(h["end"]))
                if key not in stmts:
                    stmts[key] = {"acct": h["acct"], "start": h["start"], "end": h["end"], "layout": use["name"],
                                  "kind": use.get("balance_kind", "asset"), "begin": None, "close": None,
                                  "pages": [], "rows": []}
                    order.append(key)
                s = stmts[key]
                s["pages"].append({"file": rel, "page": k + 1, "sha256": sha})
                if s["begin"] is None:
                    s["begin"] = h["begin"]
                if s["close"] is None:
                    s["close"] = h["close"]
            heads = dict((k, plan[k][1]) for k in range(i, j))
            for r in lay.parse_run(use, run):
                h = heads[r["page"]]
                key = (h["acct"], _iso(h["start"]), _iso(h["end"]))
                r["file"], r["sha256"] = rel, sha
                stmts[key]["rows"].append(r)
            i = j

    rows, statements = [], []
    for key in order:
        s = stmts[key]
        _signs(s)
        occ = {}
        for r in s["rows"]:
            y = lay.year_for(r, s["start"], s["end"])
            d = "%04d-%02d-%02d" % (y, r["mm"], r["dd"]) if y else "????-%02d-%02d" % (r["mm"], r["dd"])
            base = "|".join([str(s["acct"]), d, r["desc"], "%.2f" % r["amount"], str(r["credit"])])
            occ[base] = occ.get(base, 0) + 1
            rid = hashlib.sha1(("%s|%d" % (base, occ[base])).encode("utf-8")).hexdigest()[:8]
            rows.append({"id": rid, "acct": s["acct"], "date": d, "desc": r["desc"], "amount": round(r["amount"], 2),
                         "credit": r["credit"], "balance": r["balance"], "file": r["file"], "page": r["page"] + 1,
                         "period": [_iso(s["start"]), _iso(s["end"])], "sha256": r["sha256"]})
        statements.append(_check(s))
    rows.sort(key=lambda r: (str(r["acct"]), r["date"]))

    out = {"folder": folder, "files": files, "statements": statements, "rows": rows, "unread_pages": unread,
           "repeat_pages": repeats, "layouts": [x["name"] for x in L]}
    with open(os.path.join(work, "ledger.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    write_csv(rows, os.path.join(work, "ledger.csv"))
    text = index_text(out)
    with open(os.path.join(work, "index.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    searchlog.add(work, "read statements", folder, {
        "files": len(files), "files_read": sum(1 for f in files if f["status"] == "read"),
        "pages": sum(f["pages"] for f in files), "statements": len(statements), "lines": len(rows),
        "pages_not_read": len(unread), "repeat_pages": repeats,
        "files_not_read": [f["file"] + ": " + f["status"] for f in files if f["status"] != "read"]})
    log(text)
    return out


def _signs(s):
    """Settle debit or credit from the running balance: when the balance moves by the line's amount, the direction it moved wins."""
    prev = s["begin"]
    for r in s["rows"]:
        bal = r.get("balance")
        if bal is not None and prev is not None:
            step = bal - prev
            if abs(abs(step) - r["amount"]) < CENT and r["amount"] >= CENT:
                up = step > 0
                r["credit"] = up if s["kind"] == "asset" else (not up)
        if bal is not None:
            prev = bal


def _check(s):
    cr = sum(r["amount"] for r in s["rows"] if r["credit"] is True)
    dr = sum(r["amount"] for r in s["rows"] if r["credit"] is False)
    unknown = sum(1 for r in s["rows"] if r["credit"] is None)
    if s["begin"] is None or s["close"] is None:
        check = "no balances read"
    elif unknown:
        check = "debit or credit not read on %d lines" % unknown
    else:
        want = s["begin"] + (cr - dr if s["kind"] == "asset" else dr - cr)
        off = round(want - s["close"], 2)
        check = "reconciled" if abs(off) < CENT else "off by %s" % money(abs(off))
    return {"acct": s["acct"], "start": _iso(s["start"]), "end": _iso(s["end"]), "layout": s["layout"],
            "begin": s["begin"], "close": s["close"], "lines": len(s["rows"]), "credits": round(cr, 2),
            "debits": round(dr, 2), "check": check, "pages": s["pages"]}


def money(x):
    return "$%s" % format(x, ",.2f") if x is not None else ""


def count(n, word):
    """count(1, "page") -> "1 page"; count(3, "page") -> "3 pages"."""
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def mask(acct):
    """An account as shown in what leaves the work folder: its last four characters."""
    a = str(acct or "")
    return "…" + a[-4:] if len(a) > 4 else a


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "account", "date", "debit", "credit", "description", "balance", "file", "page"])
        for r in rows:
            amt = "%.2f" % r["amount"]
            w.writerow([r["id"], r["acct"] or "", r["date"], amt if r["credit"] is False else "",
                        amt if r["credit"] is True else "", r["desc"],
                        "" if r["balance"] is None else "%.2f" % r["balance"], r["file"], r["page"]])


def gaps(statements):
    """Per account: days between one statement's end and the next one's start, and overlaps."""
    out, by = [], {}
    for s in statements:
        if s["acct"] and s["start"] and s["end"]:
            by.setdefault(s["acct"], []).append(s)
    for acct in sorted(by):
        ss = sorted(by[acct], key=lambda s: s["start"])
        for a, b in zip(ss, ss[1:]):
            ae, bs = date.fromisoformat(a["end"]), date.fromisoformat(b["start"])
            if (bs - ae).days > 3:
                out.append({"acct": acct, "kind": "gap", "from": (ae + timedelta(days=1)).isoformat(),
                            "to": (bs - timedelta(days=1)).isoformat()})
            elif bs <= ae and b["start"] != a["start"]:
                out.append({"acct": acct, "kind": "overlap", "from": b["start"], "to": a["end"]})
    return out


def index_text(out):
    S, F = out["statements"], out["files"]
    W = []
    W.append("STATEMENTS READ")
    W.append("Folder: %s" % out["folder"])
    W.append("%s, %s, %s, %s." % (count(len(F), "file"), count(sum(f["pages"] for f in F), "page"),
                                  count(len(S), "statement"), count(len(out["rows"]), "line")))
    W.append("")
    W.append("Account and period come from the page, not from the file name.")
    W.append("")
    W.append("%-14s %-23s %6s %14s %14s  %s" % ("ACCOUNT", "PERIOD", "LINES", "OPENING", "CLOSING", "CHECK"))
    for s in sorted(S, key=lambda s: (str(s["acct"]), str(s["start"]))):
        per = "%s to %s" % (s["start"], s["end"]) if s["end"] else "period not read"
        W.append("%-14s %-23s %6d %14s %14s  %s" % (mask(s["acct"]) or "not read", per, s["lines"],
                                                    money(s["begin"]), money(s["close"]), s["check"]))
    g = gaps(S)
    W.append("")
    W.append("GAPS AND OVERLAPS")
    if not g:
        W.append("None between the statements read.")
    for x in g:
        W.append("%s  %s  %s to %s" % (mask(x["acct"]), x["kind"], x["from"], x["to"]))
    other = [f for f in F if f["status"] != "read"]
    W.append("")
    W.append("FILES NOT READ")
    if not other:
        W.append("None.")
    for f in other:
        W.append("%s — %s%s" % (f["file"], f["status"], " (%s)" % f["copy_of"] if f["copy_of"] else ""))
    W.append("")
    W.append("PAGES WITH AMOUNTS THAT NO LAYOUT READ")
    if not out["unread_pages"]:
        W.append("None.")
    for u in out["unread_pages"]:
        W.append("%s page %d — %d amounts on the page — opens: %s" % (u["file"], u["page"], u["amounts_on_page"], u.get("first_line", "")))
    if out["repeat_pages"]:
        W.append("")
        W.append("Repeats of a page already read, counted once: %d." % out["repeat_pages"])
    return "\n".join(W) + "\n"


def load(work):
    with open(os.path.join(work, "ledger.json"), encoding="utf-8") as fh:
        return json.load(fh)
