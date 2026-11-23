"""The production: the pages that carry a marked line, numbered, with an index and a log.

    unit "page"        each page that carries a line marked y (add the statement's first page with first_page)
    unit "statement"   each page of a statement that carries a line marked y

Each statement becomes one PDF. A Bates number (a prefix and a running number, one per page)
is stamped at the lower right of each page. The source files are opened for reading only.
"""
import csv
import io
import json
import os

from . import ledger, pages, piles, searchlog


def stamp(page, text):
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    w, h = float(page.mediabox.width) or 612.0, float(page.mediabox.height) or 792.0
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(w - 26, 20, text)
    c.save()
    buf.seek(0)
    page.merge_page(PdfReader(buf).pages[0])
    return page


def produce(work, prefix, start=1, unit="page", first_page=False, digits=6, replace=False, log=print):
    from pypdf import PdfReader, PdfWriter
    led = ledger.load(work)
    marks = piles.read_marks(work)
    yes = set(i for i, (m, _n) in marks.items() if m in piles.YES)
    rows = [r for r in led["rows"] if r["id"] in yes]
    if not rows:
        raise SystemExit("no line is marked y in marks.csv; nothing to produce")
    prefix = "".join(c for c in prefix.upper() if c.isalnum() or c in "-_")
    out = os.path.join(work, "production-%s-%0*d" % (prefix, digits, start))
    if os.path.isdir(out) and os.listdir(out):
        if not replace:
            raise SystemExit("%s already has a production in it; pass --replace to write over it, or a different --start" % out)
        for f in os.listdir(out):
            os.remove(os.path.join(out, f))
    os.makedirs(out, exist_ok=True)

    marked = {}
    for r in rows:
        marked.setdefault((r["acct"], r["period"][0], r["period"][1]), []).append(r)
    root = led["folder"] if os.path.isdir(led["folder"]) else os.path.dirname(led["folder"])
    n, index, left_out = start, [], []
    for s in sorted(led["statements"], key=lambda s: (str(s["acct"]), str(s["start"]))):
        got = marked.get((s["acct"], s["start"], s["end"]))
        if not got:
            continue
        want = set((r["file"], r["page"]) for r in got)
        take = []
        for i, p in enumerate(s["pages"]):
            if unit == "statement" or (p["file"], p["page"]) in want or (first_page and i == 0):
                take.append(p)
            else:
                left_out.append((s, p))
        w, first, readers = PdfWriter(), n, {}
        for p in take:
            if p["file"] not in readers:
                readers[p["file"]] = PdfReader(os.path.join(root, p["file"]))
            w.add_page(stamp(readers[p["file"]].pages[p["page"] - 1], "%s%0*d" % (prefix, digits, n)))
            n += 1
        b0, b1 = "%s%0*d" % (prefix, digits, first), "%s%0*d" % (prefix, digits, n - 1)
        name = "%s-%s_acct-%s_%s.pdf" % (b0, b1, str(s["acct"] or "none")[-4:], (s["start"] or "undated")[:7])
        with open(os.path.join(out, name), "wb") as fh:
            w.write(fh)
        index.append({"bates_start": b0, "bates_end": b1, "account": ledger.mask(s["acct"]),
                      "period": "%s to %s" % (s["start"], s["end"]), "pages": len(take), "lines_marked": len(got),
                      "source": "; ".join("%s p.%d" % (p["file"], p["page"]) for p in take),
                      "source_sha256": "; ".join(sorted(set(p["sha256"] for p in take))),
                      "output": name, "output_sha256": pages.sha256(os.path.join(out, name))})

    cols = ["bates_start", "bates_end", "account", "period", "pages", "lines_marked", "source", "source_sha256", "output", "output_sha256"]
    with open(os.path.join(out, "production-index.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(index)
    last = "%s%0*d" % (prefix, digits, n - 1)
    nxt = "%s%0*d" % (prefix, digits, n)
    C = ledger.count
    W = ["PRODUCTION INDEX", "%s%0*d to %s. %s in %s, from %s." % (
        prefix, digits, start, last, C(n - start, "page"), C(len(index), "file"), C(len(rows), "marked line")),
         "Unit: %s%s." % (unit, ", with each statement's first page" if first_page and unit == "page" else ""),
         "Next number: %s" % nxt, ""]
    for x in index:
        W.append("%s to %s   account %s   %s   %s   %s" % (
            x["bates_start"], x["bates_end"], x["account"], x["period"], C(x["pages"], "page"), C(x["lines_marked"], "marked line")))
        W.append("    from %s" % x["source"])
    W += ["", "PAGES OF THESE STATEMENTS LEFT OUT (no marked line on the page)"]
    if not left_out:
        W.append("None.")
    for s, p in left_out:
        W.append("account %s   %s to %s   %s p.%d" % (ledger.mask(s["acct"]), s["start"], s["end"], p["file"], p["page"]))
    untouched = sum(1 for s in led["statements"] if (s["acct"], s["start"], s["end"]) not in marked)
    W += ["", "Statements read with no marked line: %d." % untouched,
          "Pages are stamped as they are in the source; nothing on them is redacted."]
    text = "\n".join(W) + "\n"
    with open(os.path.join(out, "production-index.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(out, "production.json"), "w", encoding="utf-8") as fh:
        json.dump({"prefix": prefix, "start": start, "last": last, "next": nxt, "unit": unit, "files": index}, fh, indent=1)
    searchlog.add(work, "production made", out, {"range": "%s%0*d to %s" % (prefix, digits, start, last),
                                                 "pages": n - start, "files": len(index), "marked_lines": len(rows),
                                                 "statements_with_no_marked_line": untouched})
    log(text)
    return {"folder": out, "index": index, "next": nxt, "text": text}
