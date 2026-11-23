"""The statement reader: page-level filing, signs, the balance check, gaps, copies, scans."""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import make_example  # noqa: E402
from pells import layouts, ledger, searchlog  # noqa: E402

QUIET = lambda *_a: None  # noqa: E731


def example(tmp_path):
    ex = os.path.join(str(tmp_path), "ex")
    make_example.main([ex], quiet=True)
    work = os.path.join(str(tmp_path), "work")
    return ex, work, ledger.read(os.path.join(ex, "statements"), work, log=QUIET)


def by_layout(name):
    return [L for L in layouts.load() if L["name"] == name][0]


def test_counts_and_checks(tmp_path):
    _ex, _work, out = example(tmp_path)
    assert len(out["files"]) == 5
    assert len(out["statements"]) == 4
    assert len(out["rows"]) == 26
    checks = sorted(s["check"] for s in out["statements"])
    assert checks == ["off by $488.14", "reconciled", "reconciled", "reconciled"]


def test_page_decides_the_account(tmp_path):
    _ex, _work, out = example(tmp_path)
    p2 = [r for r in out["rows"] if r["file"] == "eStatement_bundle.pdf" and r["page"] == 2]
    assert p2 and all(r["acct"].endswith("5666") for r in p2)
    p3 = [r for r in out["rows"] if r["file"] == "eStatement_bundle.pdf" and r["page"] == 3]
    assert p3 and all(r["acct"].endswith("2333") and r["period"] == ["2026-01-01", "2026-01-31"] for r in p3)


def test_two_like_lines_on_one_day_are_two_lines(tmp_path):
    _ex, _work, out = example(tmp_path)
    twins = [r for r in out["rows"] if r["desc"] == "COFFEE CART 5TH ST"]
    assert len(twins) == 2 and twins[0]["id"] != twins[1]["id"]


def test_sign_comes_from_the_running_balance(tmp_path):
    _ex, _work, out = example(tmp_path)
    pay = [r for r in out["rows"] if r["desc"].startswith("PAYROLL")]
    assert pay and all(r["credit"] is True for r in pay)
    roof = [r for r in out["rows"] if r["desc"] == "RIVERBEND ROOFING CO"][0]
    assert roof["credit"] is False and roof["amount"] == 1850.00 and roof["date"] == "2026-01-15"


def test_gap_copy_scan_repeat(tmp_path):
    _ex, work, out = example(tmp_path)
    g = ledger.gaps(out["statements"])
    assert g == [{"acct": "000111222333", "kind": "gap", "from": "2026-03-01", "to": "2026-03-31"}]
    status = dict((f["file"], f["status"]) for f in out["files"])
    assert status["document (3).pdf"].startswith("same file")
    assert status["IMG_0417.pdf"].startswith("no text layer")
    assert out["repeat_pages"] == 1
    text = open(os.path.join(work, "index.txt"), encoding="utf-8").read()
    assert "gap  2026-03-01 to 2026-03-31" in text and "off by $488.14" in text
    assert "000111222333" not in text          # the index shows the last four


def test_ids_are_the_same_on_a_second_read(tmp_path):
    ex, work, out = example(tmp_path)
    again = ledger.read(os.path.join(ex, "statements"), work, log=QUIET)
    assert [r["id"] for r in out["rows"]] == [r["id"] for r in again["rows"]]
    assert len(set(r["id"] for r in out["rows"])) == 26


def test_search_log_gets_a_line_per_read(tmp_path):
    ex, work, _out = example(tmp_path)
    ledger.read(os.path.join(ex, "statements"), work, log=QUIET)
    e = searchlog.entries(work)
    assert len(e) == 2 and e[0]["what"] == "read statements"
    assert e[0]["files"] == 5 and e[0]["files_read"] == 3 and len(e[0]["files_not_read"]) == 2


def test_amount_marks():
    assert layouts.to_amount("$1,234.56") == (1234.56, "")
    assert layouts.to_amount("-45.10") == (45.10, "-")
    assert layouts.to_amount("45.10-") == (45.10, "-")
    assert layouts.to_amount("(45.10)") == (45.10, "()")
    assert layouts.to_amount("45.10 CR") == (45.10, "CR")
    assert layouts.signed("-$2.00") == -2.0


def test_line_style_minus_is_a_debit():
    L = by_layout("plain-running-balance")
    text = ("Account Number: 000444555666\nStatement Period: 01/01/2026 to 01/31/2026\n"
            "01/10  WIDGET SHOP                -20.00   980.00\n01/11  REFUND WIDGET SHOP   5.00 CR   985.00\n")
    rows = layouts.parse_line(L, text)
    assert [(r["desc"], r["amount"], r["credit"]) for r in rows] == [("WIDGET SHOP", 20.0, False), ("REFUND WIDGET SHOP", 5.0, True)]


BLOCK = """for Account Number: 0001112223
Statement Period: 03/01/2026 to 03/31/2026
Beginning Balance $1,000.00
Ending Balance $1,104.00
03/02 ATM REBATE $200.00 ATM W/D 55 MAIN ST on 03/01
0 $4.00 $1,004.00
03/05 HARDWARE DEPOT
$50.00
0
$954.00
03/09 PAYROLL
0 $150.00 $1,104.00
"""


def test_block_style_takes_the_amount_beside_the_balance():
    L = by_layout("usaa-deposit")
    h = layouts.header(L, BLOCK)
    assert h["acct"] == "0001112223" and h["start"] == date(2026, 3, 1) and h["begin"] == 1000.0 and h["close"] == 1104.0
    rows = layouts.parse_block(L, BLOCK)
    assert [(r["amount"], r["credit"], r["balance"]) for r in rows] == [(4.0, True, 1004.0), (50.0, False, 954.0), (150.0, True, 1104.0)]
    s = {"begin": 1000.0, "close": 1104.0, "kind": "asset", "rows": rows, "acct": "x", "start": h["start"], "end": h["end"],
         "layout": "usaa-deposit", "pages": []}
    ledger._signs(s)
    assert ledger._check(s)["check"] == "reconciled"


STACK = """Statement Closing Date
01/15/26
Account Number
4111 XXXX XXXX 9876
12/20
12/21
ABCDEFGH12345678
HARDWARE DEPOT
ANYTOWN CA
$45.10
01/03
01/04
ZYXWVUTS87654321
PAYMENT THANK YOU
$100.00-
"""


def test_stack_style_card():
    L = by_layout("usaa-card")
    h = layouts.header(L, STACK)
    assert h["acct"] == "card ****9876" and h["end"] == date(2026, 1, 15)
    rows = layouts.parse_run(L, [(0, STACK)])
    assert [(r["desc"], r["amount"], r["credit"]) for r in rows] == [
        ("HARDWARE DEPOT ANYTOWN CA", 45.10, False), ("PAYMENT THANK YOU", 100.0, True)]
    assert layouts.year_for(rows[0], h["start"], h["end"]) == 2025
    assert layouts.year_for(rows[1], h["start"], h["end"]) == 2026


def test_year_for_a_line_posted_before_the_period():
    row = {"mm": 11, "dd": 28, "yy": None}
    assert layouts.year_for(row, date(2025, 12, 16), date(2026, 1, 15)) == 2025
    assert layouts.year_for({"mm": 2, "dd": 29, "yy": None}, date(2024, 2, 1), date(2024, 2, 29)) == 2024
