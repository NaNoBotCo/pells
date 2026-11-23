#!/usr/bin/env python3
"""Write the example matter: made-up statements, receipts and chats for Jane Doe v. Roe Holdings, LLC.

    python3 scripts/make_example.py [out-folder]      default: examples/doe-v-roe

The bank, the accounts, the vendors and the people are invented. The folder is built to
show what the reader meets in a download from a bank portal: a bundle that mixes two accounts,
the same statement twice, a month that is absent, a statement with a page absent, and a scan.
"""
import json
import os
import shutil
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BANK = "Harbor Example Bank"
CHK, SAV = "000111222333", "000444555666"

# (date, description, amount, +1 credit / -1 debit)
JAN = [("01/03", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("01/05", "HARDWARE DEPOT #114 ROOFING NAILS", 245.10, -1),
       ("01/06", "COFFEE CART 5TH ST", 4.50, -1),
       ("01/06", "COFFEE CART 5TH ST", 4.50, -1),
       ("01/09", "NORTHFORK ELECTRIC COOP AUTOPAY", 131.22, -1),
       ("01/12", "CITY WATER DISTRICT", 58.40, -1),
       ("01/15", "RIVERBEND ROOFING CO", 1850.00, -1),
       ("01/17", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("01/20", "ATM WITHDRAWAL 5TH ST", 200.00, -1),
       ("01/22", "CHECK # 1042", 600.00, -1),
       ("01/27", "OAKLINE INSURANCE HOMEOWNERS", 212.00, -1),
       ("01/30", "TRANSFER TO SAVINGS 6666", 300.00, -1)]
FEB = [("02/03", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("02/04", "COUNTY TAX COLLECTOR PROPERTY TAX", 1422.18, -1),
       ("02/09", "NORTHFORK ELECTRIC COOP AUTOPAY", 142.87, -1),
       ("02/11", "LUMBER AND SUPPLY CO", 389.60, -1),
       ("02/12", "CITY WATER DISTRICT", 61.05, -1),
       ("02/17", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("02/19", "DELTA PLUMBING SERVICE CALL", 275.00, -1),
       ("02/24", "GROCERY OUTLET", 96.31, -1)]
APR = [("04/03", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("04/07", "PAVING BROTHERS DRIVEWAY DEPOSIT", 2500.00, -1),
       ("04/09", "NORTHFORK ELECTRIC COOP AUTOPAY", 118.02, -1),
       ("04/13", "CITY WATER DISTRICT", 57.75, -1),
       ("04/17", "PAYROLL DEPOSIT ROE HOLDINGS", 2100.00, 1),
       ("04/21", "HARDWARE DEPOT #114", 88.14, -1),
       ("04/28", "PAVING BROTHERS DRIVEWAY BALANCE", 2500.00, -1)]
SAV_JAN = [("01/30", "TRANSFER FROM CHECKING 2333", 300.00, 1),
           ("01/31", "INTEREST PAID", 1.12, 1)]


def fmt(x):
    return format(x, ",.2f")


def statement_pages(acct, period, begin, rows, per_page=8, minus=False):
    """[[line, ...], ...]: the text lines of each page. minus=True prints debits with a minus sign."""
    bal, body = begin, []
    for d, desc, amt, sign in rows:
        bal = round(bal + sign * amt, 2)
        shown = ("-" + fmt(amt)) if (minus and sign < 0) else fmt(amt)
        body.append("%-6s %-42s %12s %13s" % (d, desc, shown, fmt(bal)))
    chunks = [body[i:i + per_page] for i in range(0, len(body), per_page)] or [[]]
    out = []
    for n, chunk in enumerate(chunks):
        head = ["%s%sPage %d of %d" % (BANK, " " * 34, n + 1, len(chunks)),
                "Account Number: %s" % acct,
                "Statement Period: %s to %s" % period]
        if n == 0:
            head += ["Beginning Balance $%s" % fmt(begin), "Ending Balance $%s" % fmt(bal)]
        head += ["", "%-6s %-42s %12s %13s" % ("Date", "Description", "Amount", "Balance")]
        out.append(head + chunk)
    return out, bal


def write_pdf(path, pages):
    c = canvas.Canvas(path, pagesize=LETTER, invariant=1)
    for lines in pages:
        c.setFont("Courier", 9)
        y = 740
        for ln in lines:
            c.drawString(54, y, ln)
            y -= 13
        c.showPage()
    c.save()


def write_scan(path):
    """A page with a drawing and no text layer, as a phone scan arrives."""
    c = canvas.Canvas(path, pagesize=LETTER, invariant=1)
    c.setFillGray(0.85)
    c.rect(72, 500, 468, 220, fill=1, stroke=0)
    c.showPage()
    c.save()


def main(argv, quiet=False):
    out = os.path.abspath(argv[0]) if argv else os.path.join(ROOT, "examples", "doe-v-roe")
    st = os.path.join(out, "statements")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(st)

    jan, b1 = statement_pages(CHK, ("01/01/2026", "01/31/2026"), 5000.00, JAN)
    feb, b2 = statement_pages(CHK, ("02/01/2026", "02/28/2026"), b1, FEB)
    # no March statement: a gap
    apr, _ = statement_pages(CHK, ("04/01/2026", "04/30/2026"), round(b2 + 310.44, 2), APR, per_page=4)
    sav, _ = statement_pages(SAV, ("01/01/2026", "01/31/2026"), 12000.00, SAV_JAN, minus=True)

    write_pdf(os.path.join(st, "eStatement_bundle.pdf"), [jan[0], sav[0], jan[1]])   # two accounts in one file
    write_pdf(os.path.join(st, "document (2).pdf"), feb)
    shutil.copyfile(os.path.join(st, "document (2).pdf"), os.path.join(st, "document (3).pdf"))   # the same file twice
    write_pdf(os.path.join(st, "eStatement_bundle_2.pdf"), feb + [apr[0]])            # February again, and April page 1 only
    write_scan(os.path.join(st, "IMG_0417.pdf"))

    rc = os.path.join(out, "receipts")
    os.makedirs(rc)
    with open(os.path.join(rc, "riverbend-invoice.txt"), "w", encoding="utf-8") as fh:
        fh.write("RIVERBEND ROOFING CO\nInvoice 2291\nDate: 01/14/2026\nTear-off and re-roof, north slope\n"
                 "Subtotal $1,850.00\nTotal $1,850.00\nPaid by card on file\n")
    with open(os.path.join(rc, "delta-plumbing.txt"), "w", encoding="utf-8") as fh:
        fh.write("Delta Plumbing\nService call, kitchen supply line\nFebruary 18, 2026\nAmount due: $275.00\n")
    with open(os.path.join(rc, "tree-crew-cash.txt"), "w", encoding="utf-8") as fh:
        fh.write("Hillside Tree Crew\n3 pines down and hauled\n2026-03-08\nTOTAL 900.00 CASH\n")
    write_pdf(os.path.join(rc, "lumber-and-supply.pdf"),
              [["LUMBER AND SUPPLY CO", "Receipt 88104", "02/10/2026", "2x6 DF #2  24 pc", "Tax 28.86", "Total 389.60"]])

    th = os.path.join(out, "chats", "messages", "inbox", "riverbendroofing_10001")
    os.makedirs(th)
    msgs = [("Jane Doe", 1767916800000, "Can you quote the north slope? Shingles are lifting."),
            ("Riverbend Roofing", 1768003200000, "Estimate is $1,850 for tear-off and re-roof."),
            ("Jane Doe", 1768348800000, "Go ahead. Paid the invoice today, receipt attached."),
            ("Riverbend Roofing", 1768435200000, "Got it, thanks. Crew is booked for Thursday.")]
    with open(os.path.join(th, "message_1.json"), "w", encoding="utf-8") as fh:
        json.dump({"participants": [{"name": "Jane Doe"}, {"name": "Riverbend Roofing"}], "title": "Riverbend Roofing",
                   "messages": [{"sender_name": s, "timestamp_ms": t, "content": c} for s, t, c in reversed(msgs)]}, fh, indent=1)
    th2 = os.path.join(out, "chats", "messages", "inbox", "samlee_10002")
    os.makedirs(th2)
    with open(os.path.join(th2, "message_1.json"), "w", encoding="utf-8") as fh:
        json.dump({"participants": [{"name": "Jane Doe"}, {"name": "Sam Lee"}], "title": "Sam Lee",
                   "messages": [{"sender_name": "Sam Lee", "timestamp_ms": 1769040000000, "content": "Trivia night Friday?"},
                                {"sender_name": "Jane Doe", "timestamp_ms": 1769043600000, "content": "Yes. I'll bring the roof story."}]}, fh, indent=1)
    with open(os.path.join(out, "chats", "paving-brothers.txt"), "w", encoding="utf-8") as fh:
        fh.write("[4/2/26, 9:14:02 AM] Jane Doe: How much to pave the driveway, about 60 feet?\n"
                 "[4/2/26, 9:40:11 AM] Paving Brothers: $5,000, half up front.\n"
                 "[4/6/26, 5:02:45 PM] Jane Doe: Sending the deposit tomorrow.\n"
                 "[4/28/26, 3:30:00 PM] Paving Brothers: Driveway is done. Balance due.\n")
    if not quiet:
        print("example written to %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
