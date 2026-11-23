#!/usr/bin/env python3
"""Writes docs/, the public page: the desk window showing the example matter.

    python3 scripts/make_site.py

Runs the engine on examples/doe-v-roe (read, piles, the building-trades pile marked, a production,
receipts, chats), puts what the desk would show into desk/index.html as DEMO, and copies the
production the engine wrote into docs/samples/. The page calls no server.
"""
import csv
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pells import chats, desk, ledger, piles, produce, receipts, searchlog  # noqa: E402

SITE = "https://nanobotco.github.io/pells/"
KIT = "https://github.com/NaNoBotCo/pells"
PILE = "building trades"
QUIET = lambda *_a: None  # noqa: E731

HEAD = """<title>Pells</title>
<meta name="description" content="Bank and card statements in. A ledger checked against the printed balances, and a Bates-numbered set of pages, out. A kit for a Mac, shown here on a made-up matter.">
<link rel="canonical" href="{site}">
<meta property="og:type" content="website"><meta property="og:site_name" content="NaNoBotCo">
<meta property="og:title" content="Pells · เพลส์">
<meta property="og:description" content="Statements in; a checked ledger and a numbered production out. · จากใบแจ้งยอดสู่ชุดเอกสารใส่เลขหน้า">
<meta property="og:url" content="{site}">
<meta property="og:image" content="{site}card.jpg">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="A ledger sheet with ruled columns and the word Pells.">
<meta property="og:locale" content="en_US"><meta property="og:locale:alternate" content="th_TH">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{site}card.jpg">
<link rel="alternate" type="text/plain" href="{site}llms.txt" title="llms.txt">"""

LLMS = """# Pells · เพลส์

Bank and card statements in. A ledger checked against the printed balances, and a numbered set of pages for the other side, out. A kit for a Mac (Python 3.9, pypdf, reportlab), in English and Thai. This page shows it on a fictional matter, Doe v. Roe Holdings, LLC.

- Reads the page, not the file name: each line is filed under the account and period printed on its own page, so a bundle of two accounts, a repeat download or an absent month shows up as what it is.
- Checks the arithmetic: opening balance plus the lines against the closing balance printed on each statement; the index says "reconciled" or "off by" an amount.
- Lists what it did not read: scans with no text layer, copies of another file, pages with amounts that match no layout.
- Piles: word matches (utilities, building trades, cash, checks) as reasons to read a line; marks of produce, leave out or come back carry across rebuilds.
- Production: pages that carry a marked line get a Bates number, with an index tying each number to its source file and page and SHA-256 hashes of source and output.
- Receipts paired to ledger lines by amount and date; chat exports searched by subject words and sorted into tiers; a search log with one entry per thing read.
- A statement layout is one JSON file per bank.

Pages are stamped as they are in the source. Pells does not redact.

Kit: {kit}
Sibling: Cursitor, a litigation desk for Claude Code, https://nanobotco.github.io/cursitor/

Text CC BY 4.0, code MIT.
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{site}</loc><lastmod>{day}</lastmod></url>
</urlset>
"""


def main():
    import datetime
    work = tempfile.mkdtemp(prefix="pells-site-")
    example = os.path.join(ROOT, "examples", "doe-v-roe")
    docs = os.path.join(ROOT, "docs")
    try:
        ledger.read(os.path.join(example, "statements"), work, log=QUIET)
        piles.build(work, log=QUIET)
        with open(os.path.join(work, "marks.csv"), encoding="utf-8", newline="") as fh:
            ids = set(r["id"] for r in csv.DictReader(fh) if PILE in r["pile"].lower())
        piles.set_mark(work, ids, "y")
        piles.build(work, log=QUIET)
        desk.State.work = work
        opened = desk.state()
        res = produce.produce(work, "DOE", 1, "page", True, 6, False, log=QUIET)
        made = desk.state()
        receipts.pair(os.path.join(example, "receipts"), work, log=QUIET)
        chats.search(os.path.join(example, "chats"), work, log=QUIET)

        def read(name):
            with open(os.path.join(work, name), encoding="utf-8") as fh:
                return fh.read()

        demo = {"kit": KIT, "state": opened, "productions": made["productions"], "production_text": res["text"],
                "receipts": read("receipts.txt"), "chats": read("chats.txt"), "log": searchlog.render(work)}

        def clean(text):
            for real in (os.path.realpath(work), work):
                text = text.replace(real, "Pells-work")
            for real in (os.path.realpath(ROOT), ROOT):
                text = text.replace(real, "pells")
            return text

        blob = clean(json.dumps(demo, ensure_ascii=False)).replace("</", "<\\/")
        for bad in ("/Users/", "/private/", "/var/folders", "/tmp/"):
            if bad in blob:
                raise SystemExit("a path from this computer is in the page data: %s" % bad)

        with open(os.path.join(ROOT, "desk", "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        for old, new in (("<title>Pells</title>", HEAD.format(site=SITE)),
                         ("const DEMO = null;", "const DEMO = %s;" % blob),
                         ('const TOKEN = "{{TOKEN}}";', 'const TOKEN = "";')):
            if page.count(old) != 1:
                raise SystemExit("desk/index.html no longer has the line: %s" % old)
            page = page.replace(old, new)

        samples = os.path.join(docs, "samples")
        if os.path.isdir(samples):
            shutil.rmtree(samples)
        for p in made["productions"]:
            for rel in [p["index"]] + p["files"]:
                dst = os.path.join(samples, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if rel.endswith(".txt"):
                    with open(dst, "w", encoding="utf-8") as fh:
                        fh.write(clean(read(rel)))
                else:
                    shutil.copyfile(os.path.join(work, rel), dst)
        os.makedirs(docs, exist_ok=True)
        day = datetime.date.today().isoformat()
        for name, body in (("index.html", page), ("llms.txt", LLMS.format(kit=KIT)),
                           ("sitemap.xml", SITEMAP.format(site=SITE, day=day))):
            with open(os.path.join(docs, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        print("wrote %s" % docs)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
