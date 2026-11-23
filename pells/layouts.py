"""Statement layouts: one JSON table per bank format, read from layouts/*.json.

A layout says how to spot its pages (`detect`), where the account, the period and the
balances are printed, and how one transaction is laid out (`txn.style`):

    line    one transaction per line: date, description, amount, running balance
    block   a transaction starts at a line that opens with MM/DD and runs to the next one
    stack   one field per line: date, post date, reference, description, amount

The page is what gets read. A file name is not used for the account or the period.
"""
import json
import os
import re
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONEYISH = re.compile(r"\d[\d,]*\.\d{2}")


def to_amount(s):
    """'$1,234.56-' -> (1234.56, '-'). The mark is '', '-', '()', 'CR' or 'DR'."""
    s = (s or "").strip()
    mark = ""
    up = s.upper()
    if up.endswith("CR"):
        mark, s = "CR", s[:-2]
    elif up.endswith("DR"):
        mark, s = "DR", s[:-2]
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        mark, s = "()", s[1:-1]
    if s.startswith("-") or s.endswith("-"):
        mark, s = "-", s.strip("-")
    s = s.replace("$", "").replace(",", "").strip()
    return float(s), mark


def signed(s):
    v, mark = to_amount(s)
    return -v if mark in ("-", "()", "DR") else v


def _rx(pattern, flags=0):
    return re.compile(pattern, flags) if pattern else None


def compile_layout(L):
    L["_detect"] = _rx(L["detect"])
    L["_account"] = _rx(L.get("account"))
    L["_period"] = _rx(L.get("period"))
    L["_closing"] = _rx(L.get("closing"))
    L["_begin"] = _rx(L.get("begin"))
    L["_end"] = _rx(L.get("end"))
    t = L["txn"]
    t["_skip"] = [s.lower() for s in t.get("skip", [])]
    if t["style"] == "line":
        t["_row"] = re.compile(t["row"], re.M)
    elif t["style"] == "block":
        t["_start"] = re.compile(t["start"], re.M)
        t["_money"] = re.compile(t["money"])
    elif t["style"] == "stack":
        t["_date"] = re.compile(t["date"])
        t["_ref"] = _rx(t.get("ref"))
        t["_amount"] = re.compile(t["amount"])
    else:
        raise ValueError("layout %s: txn.style %r is not line, block or stack" % (L.get("name"), t["style"]))
    return L


def load(extra_dirs=()):
    """Layouts from the app's layouts/ folder, then from each extra folder. Lower priority reads first."""
    out = []
    for d in [os.path.join(ROOT, "layouts")] + [x for x in extra_dirs if x]:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    L = json.load(fh)
                L["_file"] = os.path.join(d, f)
                out.append(compile_layout(L))
    out.sort(key=lambda L: (L.get("priority", 50), L["name"]))
    return out


def pick(layouts, text):
    for L in layouts:
        if L["_detect"].search(text):
            return L
    return None


def _year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


def _dates(groups, roles):
    """Regex groups plus their roles ('m','d','y' in order) -> list of dates."""
    out, cur = [], {}
    for g, r in zip(groups, roles):
        cur[r] = g
        if len(cur) == 3:
            out.append(date(_year(cur["y"]), int(cur["m"]), int(cur["d"])))
            cur = {}
    return out


def _month_before(d):
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day) + timedelta(days=1)
        except ValueError:
            continue


def header(L, text):
    """What one page prints about itself: account, period, opening and closing balance."""
    h = {"acct": None, "start": None, "end": None, "begin": None, "close": None}
    if L["_account"]:
        m = L["_account"].search(text)
        if m:
            h["acct"] = (L.get("account_format") or "{0}").format(*m.groups())
    if L["_period"]:
        m = L["_period"].search(text)
        if m:
            ds = _dates(m.groups(), L.get("period_groups") or ["m", "d", "y", "m", "d", "y"])
            if len(ds) == 2:
                h["start"], h["end"] = ds
    if h["end"] is None and L["_closing"]:
        m = L["_closing"].search(text)
        if m:
            ds = _dates(m.groups(), L.get("closing_groups") or ["m", "d", "y"])
            if ds:
                h["end"] = ds[0]
                h["start"] = _month_before(ds[0])
    for k, rx in (("begin", L["_begin"]), ("close", L["_end"])):
        if rx:
            m = rx.search(text)
            if m:
                try:
                    h[k] = signed(m.group(1))
                except ValueError:
                    pass
    return h


def _credit(mark, rule):
    if rule == "minus_debit":
        return mark not in ("-", "()", "DR")
    if rule == "minus_credit":
        return mark in ("-", "CR")
    # "balance": a mark settles it, otherwise the running balance does, in ledger.py
    if mark in ("-", "()", "DR"):
        return False
    if mark == "CR":
        return True
    return None


def _skip(t, desc):
    low = desc.lower()
    return any(s in low for s in t["_skip"])


def parse_line(L, text):
    t = L["txn"]
    rows = []
    for m in t["_row"].finditer(text):
        g = m.groupdict()
        desc = re.sub(r"\s+", " ", g.get("desc") or "").strip()
        if not desc or _skip(t, desc):
            continue
        try:
            val, mark = to_amount(g["amt"])
        except ValueError:
            continue
        bal = None
        if g.get("bal"):
            try:
                bal = signed(g["bal"])
            except ValueError:
                bal = None
        rows.append({"mm": int(g["m"]), "dd": int(g["d"]), "yy": _year(g["y"]) if g.get("y") else None,
                     "desc": desc, "amount": val, "credit": _credit(mark, t.get("sign", "balance")), "balance": bal})
    return rows


def parse_block(L, text):
    """A transaction opens at MM/DD and runs to the next opening line.

    With credit_rule 'two_on_last_line': a debit's last money line carries one amount
    (the balance sits on its own line) and a credit's carries two (amount, then balance).
    """
    t = L["txn"]
    rows = []
    marks = list(t["_start"].finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        block = text[m.start():end]
        body = re.sub(r"\s+", " ", " ".join(x.strip() for x in block.splitlines())).strip()
        if _skip(t, body):
            continue
        amts = t["_money"].findall(block)
        if not amts:
            continue
        money_lines = [ln for ln in block.splitlines() if t["_money"].search(ln)]
        rule = t.get("credit_rule", "two_on_last_line")
        if rule == "two_on_last_line":
            credit = len(t["_money"].findall(money_lines[-1])) >= 2
        else:
            credit = None
        # the amount sits next to the balance; an earlier figure belongs to the description
        val = float(amts[-2 if len(amts) > 1 else 0].replace(",", ""))
        bal = float(amts[-1].replace(",", "")) if len(amts) > 1 else None
        rows.append({"mm": int(m.group(1)), "dd": int(m.group(2)), "yy": None, "desc": body[:300],
                     "amount": val, "credit": credit, "balance": bal})
    return rows


def parse_stack(L, numbered):
    """numbered: [(page index, line), ...] for a run of pages. One field per line."""
    t = L["txn"]
    lines = [(p, ln.strip()) for p, ln in numbered]
    rows, i, span = [], 0, int(t.get("max_desc_lines", 5))
    need_ref = t["_ref"] is not None
    while i < len(lines) - 3:
        ok = t["_date"].match(lines[i][1]) and t["_date"].match(lines[i + 1][1])
        j = i + 2
        if ok and need_ref:
            ok = bool(t["_ref"].match(lines[j][1]))
            j += 1
        if ok:
            parts = []
            while j < len(lines) and len(parts) <= span and not t["_amount"].match(lines[j][1]):
                if lines[j][1]:
                    parts.append(lines[j][1])
                j += 1
            if j < len(lines) and t["_amount"].match(lines[j][1]):
                m = t["_amount"].match(lines[j][1])
                desc = " ".join(parts)[:300]
                mm, dd = lines[i][1].split("/")[:2]
                if desc and not _skip(t, desc):
                    rows.append({"mm": int(mm), "dd": int(dd), "yy": None, "desc": desc,
                                 "amount": float(m.group(1).replace(",", "")),
                                 "credit": bool(m.group(2)) if m.lastindex and m.lastindex >= 2 else None,
                                 "balance": None, "page": lines[i][0]})
                i = j + 1
                continue
        i += 1
    return rows


def parse_run(L, run):
    """run: [(page index, text), ...], consecutive pages of one layout. Rows carry 'page'."""
    style = L["txn"]["style"]
    if style == "stack":
        numbered = [(p, ln) for p, text in run for ln in text.splitlines()]
        return parse_stack(L, numbered)
    rows = []
    for p, text in run:
        got = parse_line(L, text) if style == "line" else parse_block(L, text)
        for r in got:
            r["page"] = p
        rows.extend(got)
    return rows


def year_for(row, start, end):
    """The year of a row that prints only MM/DD: the latest year that puts it on or before the period's end (10 days of grace)."""
    if row.get("yy"):
        return row["yy"]
    if not end:
        return None
    for y in (end.year + 1, end.year, end.year - 1):
        try:
            d = date(y, row["mm"], row["dd"])
        except ValueError:
            continue
        if d <= end + timedelta(days=10):
            return y
    return end.year - 1
