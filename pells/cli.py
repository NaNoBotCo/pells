"""pells <command>: the command line. Each command works in a work folder (default ./pells-work)."""
import argparse
import os
import shutil
import subprocess
import sys

from . import __version__, chats, layouts, ledger, piles, produce, receipts, searchlog


def _work(a):
    return os.path.abspath(os.path.expanduser(a.work))


def _need(work, name, first):
    if not os.path.exists(os.path.join(work, name)):
        raise SystemExit("%s has no %s yet; run `pells %s` first" % (work, name, first))


def cmd_read(a):
    ledger.read(a.folder, _work(a), a.layouts)
    return 0


def cmd_piles(a):
    _need(_work(a), "ledger.json", "read <folder>")
    piles.build(_work(a), a.rules)
    return 0


def cmd_mark(a):
    work = _work(a)
    _need(work, "marks.csv", "piles")
    value = "y" if a.yes else "n" if a.no else "?"
    ids = set(a.ids)
    if a.pile:
        import csv
        with open(os.path.join(work, "marks.csv"), encoding="utf-8", newline="") as fh:
            ids |= set(r["id"] for r in csv.DictReader(fh) if a.pile.lower() in r["pile"].lower())
    n = piles.set_mark(work, ids, value, a.note)
    print("%d line%s marked %s" % (n, "" if n == 1 else "s", value))
    return 0 if n else 1


def cmd_produce(a):
    work = _work(a)
    _need(work, "marks.csv", "piles")
    produce.produce(work, a.prefix, a.start, a.unit, a.first_page, a.digits, a.replace)
    return 0


def cmd_receipts(a):
    _need(_work(a), "ledger.json", "read <folder>")
    receipts.pair(a.folder, _work(a), a.days_before, a.days_after)
    return 0


def cmd_chats(a):
    chats.search(a.folder, _work(a), a.terms)
    return 0


def cmd_log(a):
    print(searchlog.render(_work(a)))
    return 0


def cmd_layouts(a):
    for L in layouts.load([a.layouts, os.path.join(_work(a), "layouts")]):
        print("%-24s %-6s %s" % (L["name"], L["txn"]["style"], L.get("label", "")))
        print("    %s" % L["_file"])
    return 0


def cmd_ocr(a):
    exe = shutil.which("ocrmypdf")
    if not exe:
        print("ocrmypdf is not installed. Install it with: python3 -m pip install --user ocrmypdf  (it needs tesseract: brew install tesseract)")
        return 1
    code = 0
    for f in a.files:
        out = os.path.splitext(f)[0] + ".ocr.pdf"
        r = subprocess.run([exe, "--skip-text", f, out], capture_output=True, text=True)
        print("%s -> %s" % (f, out) if r.returncode == 0 else "%s: ocrmypdf stopped: %s" % (f, (r.stderr or "").strip()[-200:]))
        code = code or r.returncode
    return code


def cmd_desk(a):
    from . import desk
    return desk.serve(a.port, _work(a), not a.no_open)


def main(argv=None):
    P = argparse.ArgumentParser(prog="pells", description="Statements in, a checked ledger and a numbered production out.")
    P.add_argument("--version", action="version", version="pells " + __version__)
    S = P.add_subparsers(dest="cmd", metavar="<command>")

    def add(name, fn, help_):
        p = S.add_parser(name, help=help_)
        p.add_argument("--work", default="pells-work", help="work folder (default ./pells-work)")
        p.set_defaults(fn=fn)
        return p

    p = add("read", cmd_read, "read a folder of statement PDFs into a ledger and an index")
    p.add_argument("folder")
    p.add_argument("--layouts", help="a folder of extra layout tables")
    p = add("piles", cmd_piles, "sort the ledger into piles; write piles.txt and marks.csv")
    p.add_argument("--rules", help="a piles.json to use")
    p = add("mark", cmd_mark, "mark lines y, n or ? by id, or a whole pile")
    p.add_argument("ids", nargs="*")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yes", action="store_true")
    g.add_argument("--no", action="store_true")
    g.add_argument("--ask", action="store_true")
    p.add_argument("--pile", help="mark each line of the piles whose name contains these words")
    p.add_argument("--note")
    p = add("produce", cmd_produce, "number and write the pages that carry a marked line")
    p.add_argument("--prefix", required=True, help="Bates prefix, e.g. DOE")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--digits", type=int, default=6)
    p.add_argument("--unit", choices=["page", "statement"], default="page")
    p.add_argument("--first-page", action="store_true", help="with --unit page, add each statement's first page")
    p.add_argument("--replace", action="store_true")
    p = add("receipts", cmd_receipts, "read receipts and pair each with a ledger line")
    p.add_argument("folder")
    p.add_argument("--days-before", type=int, default=3)
    p.add_argument("--days-after", type=int, default=10)
    p = add("chats", cmd_chats, "search a chat export and sort the threads into tiers")
    p.add_argument("folder")
    p.add_argument("--terms", help="a chat_terms.json to use")
    add("log", cmd_log, "print the search log")
    p = add("layouts", cmd_layouts, "list the statement layouts")
    p.add_argument("--layouts", help="a folder of extra layout tables")
    p = S.add_parser("ocr", help="put a text layer on scanned PDFs (needs ocrmypdf)")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_ocr)
    p = add("desk", cmd_desk, "large-type window in the browser, on this computer")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--no-open", action="store_true")

    a = P.parse_args(argv)
    if not getattr(a, "fn", None):
        P.print_help()
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
