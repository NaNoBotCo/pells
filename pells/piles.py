"""Sort ledger lines into piles for reading, and carry the reader's marks.

A pile is a word match: a reason to read a line. Lines that match no pile are listed too,
under their own heading, so the unmatched ones get read as well.

    marks.csv   one row per ledger line; the reader fills `produce` (y, n or ?) and `note`.
                A rebuild carries those two columns over by line id.
    piles.txt   totals by pile, then each pile's lines.
"""
import csv
import json
import os
import re

from . import ledger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NO_PILE = "No pile: read by hand"
YES = ("y", "yes", "x", "1", "produce")


def load_rules(work=None, path=None):
    for p in (path, os.path.join(work, "piles.json") if work else None, os.path.join(ROOT, "rules", "piles.json")):
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            rules = []
            for r in data["piles"]:
                rules.append((r["pile"], r.get("side", "both"), [re.compile(x, re.I) for x in r["patterns"]]))
            return rules, p
    raise SystemExit("no piles.json found")


def pile_for(row, rules):
    side = "credit" if row["credit"] is True else "debit" if row["credit"] is False else "both"
    for name, want, pats in rules:
        if want != "both" and side != "both" and want != side:
            continue
        if any(p.search(row["desc"]) for p in pats):
            return name
    return NO_PILE


def read_marks(work):
    """{line id: (produce, note)} from marks.csv, or {} when there is none yet."""
    p = os.path.join(work, "marks.csv")
    out = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                out[r["id"]] = ((r.get("produce") or "").strip().lower(), r.get("note") or "")
    return out


def set_mark(work, ids, value, note=None):
    """Mark lines y, n or ?. Returns the number of lines changed."""
    p = os.path.join(work, "marks.csv")
    with open(p, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        cols, rows = rd.fieldnames, list(rd)
    n = 0
    for r in rows:
        if r["id"] in ids:
            r["produce"] = value
            if note is not None:
                r["note"] = note
            n += 1
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return n


def build(work, rules_path=None, log=print):
    led = ledger.load(work)
    rules, src = load_rules(work, rules_path)
    old = read_marks(work)
    order = [name for name, _s, _p in rules] + [NO_PILE]
    by = dict((name, []) for name in order)
    for r in led["rows"]:
        r["pile"] = pile_for(r, rules)
        by[r["pile"]].append(r)

    with open(os.path.join(work, "marks.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "produce", "note", "pile", "date", "account", "debit", "credit", "description", "file", "page"])
        for name in order:
            for r in by[name]:
                mark, note = old.get(r["id"], ("", ""))
                amt = "%.2f" % r["amount"]
                w.writerow([r["id"], mark, note, name, r["date"], ledger.mask(r["acct"]),
                            amt if r["credit"] is False else "", amt if r["credit"] is True else "",
                            r["desc"], r["file"], r["page"]])

    W = ["PILES", "Rules: %s" % src, "%d lines in the ledger." % len(led["rows"]), "",
         "A pile is a word match: a reason to read the line. The last pile lists the lines that matched no rule.",
         "Mark lines in marks.csv: y to produce, n to leave out, ? to come back to.", "",
         "%-44s %6s %14s %14s" % ("PILE", "LINES", "DEBITS", "CREDITS")]
    for name in order:
        rs = by[name]
        if not rs:
            continue
        W.append("%-44s %6d %14s %14s" % (name[:44], len(rs),
                                           ledger.money(sum(r["amount"] for r in rs if r["credit"] is False)),
                                           ledger.money(sum(r["amount"] for r in rs if r["credit"] is True))))
    for name in order:
        rs = by[name]
        if not rs:
            continue
        W += ["", name.upper()]
        for r in rs:
            mark = old.get(r["id"], ("", ""))[0]
            W.append("%-2s %s  %s  %-6s %12s  %s  (%s p.%d)  %s" % (
                mark or "·", r["id"], r["date"], ledger.mask(r["acct"]), ledger.money(r["amount"]),
                "cr" if r["credit"] is True else "dr" if r["credit"] is False else "??", r["file"], r["page"], r["desc"][:90]))
    text = "\n".join(W) + "\n"
    with open(os.path.join(work, "piles.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    log(text)
    return by
