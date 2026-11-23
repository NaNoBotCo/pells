"""Piles, marks, the numbered production, receipts and chats."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import make_example  # noqa: E402
from pells import chats, ledger, pages, piles, produce, receipts, searchlog  # noqa: E402

QUIET = lambda *_a: None  # noqa: E731


def setup(tmp_path):
    ex = os.path.join(str(tmp_path), "ex")
    make_example.main([ex], quiet=True)
    work = os.path.join(str(tmp_path), "work")
    ledger.read(os.path.join(ex, "statements"), work, log=QUIET)
    by = piles.build(work, log=QUIET)
    return ex, work, by


def ids_in(by, words):
    return set(r["id"] for name, rows in by.items() if words in name.lower() for r in rows)


def test_piles_first_match_and_the_unmatched_pile(tmp_path):
    _ex, _work, by = setup(tmp_path)
    trades = [r["desc"] for r in by["Building trades: roof, paving, plumbing, electric, trees"]]
    assert "RIVERBEND ROOFING CO" in trades and "HARDWARE DEPOT #114 ROOFING NAILS" in trades
    assert len(by[piles.NO_PILE]) == 3
    assert sum(len(v) for v in by.values()) == 26
    pay = by["Pay and deposits in"]
    assert pay and all(r["credit"] is True for r in pay)


def test_marks_carry_over_a_rebuild(tmp_path):
    _ex, work, by = setup(tmp_path)
    ids = ids_in(by, "building trades")
    assert piles.set_mark(work, ids, "y", "roof and driveway") == 4
    piles.build(work, log=QUIET)
    marks = piles.read_marks(work)
    assert all(marks[i] == ("y", "roof and driveway") for i in ids)
    assert sum(1 for m, _n in marks.values() if m == "y") == 4


def test_production_numbers_pages_and_leaves_sources_alone(tmp_path):
    from pypdf import PdfReader
    ex, work, by = setup(tmp_path)
    src = os.path.join(ex, "statements")
    before = dict((f, pages.sha256(os.path.join(src, f))) for f in os.listdir(src))
    piles.set_mark(work, ids_in(by, "building trades"), "y")
    res = produce.produce(work, "doe", first_page=True, log=QUIET)
    assert res["next"] == "DOE000004"
    assert [x["bates_start"] for x in res["index"]] == ["DOE000001", "DOE000002", "DOE000003"]
    stamped = []
    for x in res["index"]:
        for pg in PdfReader(os.path.join(res["folder"], x["output"])).pages:
            stamped.append((pg.extract_text() or "").strip().splitlines()[-1])
    assert stamped == ["DOE000001", "DOE000002", "DOE000003"]
    assert before == dict((f, pages.sha256(os.path.join(src, f))) for f in os.listdir(src))
    text = open(os.path.join(res["folder"], "production-index.txt"), encoding="utf-8").read()
    assert "eStatement_bundle.pdf p.3" in text       # the January page with no marked line is listed as left out
    assert "000111222333" not in text
    assert searchlog.entries(work)[-1]["what"] == "production made"


def test_production_refuses_to_write_over_one(tmp_path):
    _ex, work, by = setup(tmp_path)
    piles.set_mark(work, ids_in(by, "hardware"), "y")
    produce.produce(work, "DOE", log=QUIET)
    try:
        produce.produce(work, "DOE", log=QUIET)
    except SystemExit as exc:
        assert "--replace" in str(exc)
    else:
        raise AssertionError("a second production over the first was written")
    produce.produce(work, "DOE", replace=True, log=QUIET)
    produce.produce(work, "DOE", start=50, unit="statement", log=QUIET)
    data = json.load(open(os.path.join(work, "production-DOE-000050", "production.json"), encoding="utf-8"))
    assert data["files"][0]["bates_start"] == "DOE000050" and data["unit"] == "statement"


def test_production_needs_a_marked_line(tmp_path):
    _ex, work, _by = setup(tmp_path)
    try:
        produce.produce(work, "DOE", log=QUIET)
    except SystemExit as exc:
        assert "nothing to produce" in str(exc)
    else:
        raise AssertionError("a production with no marked line was written")


def test_receipts_pair_by_amount_and_date(tmp_path):
    ex, work, _by = setup(tmp_path)
    out = dict((r["file"], r) for r in receipts.pair(os.path.join(ex, "receipts"), work, log=QUIET))
    assert out["riverbend-invoice.txt"]["status"] == "paired" and out["riverbend-invoice.txt"]["date"] == "2026-01-14"
    assert out["delta-plumbing.txt"]["status"] == "paired" and out["delta-plumbing.txt"]["total"] == "275.00"
    assert out["lumber-and-supply.pdf"]["status"] == "paired"
    assert out["tree-crew-cash.txt"]["status"].startswith("no ledger line") and out["tree-crew-cash.txt"]["total"] == "900.00"


def test_receipt_reading():
    assert receipts.find_total("Subtotal $10.00\nTax 0.80\nTotal $10.80\n") == 10.80
    assert receipts.find_total("Widget 4.00\nGadget 19.50\n") == 19.50
    assert receipts.find_date("March 8, 2026").isoformat() == "2026-03-08"
    assert receipts.find_date("8 Mar 2026").isoformat() == "2026-03-08"
    assert receipts.find_date("no date here") is None


def test_chats_tiers_and_staging(tmp_path):
    ex, work, _by = setup(tmp_path)
    rows = chats.search(os.path.join(ex, "chats"), work, log=QUIET)
    got = dict((r["thread"], r["tier"]) for r in rows)
    assert got == {"Riverbend Roofing": "A", "paving-brothers": "A", "Sam Lee": "C"}
    staged = open(os.path.join(work, "chats-staged", "A-Riverbend-Roofing.txt"), encoding="utf-8").read()
    assert ">> 2026-01-10  Riverbend Roofing: Estimate is $1,850" in staged
    assert searchlog.entries(work)[-1]["threads_read"] == 3


def test_messenger_text_is_put_back_to_utf8():
    assert chats._fix("cafÃ©") == "café"
    assert chats._fix("plain") == "plain"
