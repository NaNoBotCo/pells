"""Receipts and invoices: read each one's date and total, then pair it with a ledger line.

    pair(folder, work)   reads .txt, .pdf and image files; writes receipts.csv and receipts.txt

A pair is a ledger line for the same amount, dated from 3 days before the receipt to 10 days
after it (both settable). A receipt with no line in that window is listed as such: it may
have been paid in cash or from an account that is not in the ledger.
"""
import csv
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

from . import ledger, searchlog

IMAGES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp")
MONTHS = dict((m, i + 1) for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]))
MONEY = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})")
TOTAL = re.compile(r"\b(grand total|total due|amount due|balance due|amount paid|total paid|total|paid)\b", re.I)
D_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
D_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
D_MDY = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2}),? (20\d{2})\b")
D_DMY = re.compile(r"\b(\d{1,2}) ([A-Za-z]{3,9})\.?,? (20\d{2})\b")


def text_of(path):
    """(text, note). The note says why there is no text, when there is none."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(), ""
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
        except Exception:
            return "", "did not open as a PDF"
        return (text, "") if len(text.strip()) >= 20 else ("", "no text layer (a scan); run OCR first")
    if ext in IMAGES:
        exe = shutil.which("tesseract")
        if not exe:
            return "", "a picture; install tesseract to read it"
        try:
            r = subprocess.run([exe, path, "stdout"], capture_output=True, text=True, timeout=120)
            return r.stdout, "" if r.stdout.strip() else "tesseract read no words"
        except Exception:
            return "", "tesseract did not finish"
    return "", "not a .txt, .pdf or picture"


def find_date(text):
    def ok(y, m, d):
        try:
            return date(y + 2000 if y < 100 else y, m, d)
        except ValueError:
            return None
    for rx, order in ((D_ISO, "ymd"), (D_NUM, "mdy")):
        m = rx.search(text)
        if m:
            a, b, c = [int(x) for x in m.groups()]
            got = ok(a, b, c) if order == "ymd" else ok(c, a, b)
            if got:
                return got
    m = D_MDY.search(text)
    if m and m.group(1)[:3].lower() in MONTHS:
        return ok(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = D_DMY.search(text)
    if m and m.group(2)[:3].lower() in MONTHS:
        return ok(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    return None


def find_total(text):
    """The amount on the last line that says total, amount due or paid; else the largest amount."""
    best = None
    for ln in text.splitlines():
        if TOTAL.search(ln) and not re.search(r"sub\s?-?total", ln, re.I):
            m = MONEY.findall(ln)
            if m:
                best = float(m[-1].replace(",", ""))
    if best is not None:
        return best
    allm = [float(x.replace(",", "")) for x in MONEY.findall(text)]
    return max(allm) if allm else None


def vendor(text):
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()[:60]
    return ""


def fits(rdate, total, rows, before=3, after=10):
    out = []
    for r in rows:
        if abs(r["amount"] - total) >= 0.005 or r["credit"] is True:
            continue
        if rdate is None or r["date"].startswith("?"):
            out.append(r)
            continue
        d = date.fromisoformat(r["date"])
        if rdate - timedelta(days=before) <= d <= rdate + timedelta(days=after):
            out.append(r)
    return out


def pair(folder, work, before=3, after=10, log=print):
    folder = os.path.abspath(os.path.expanduser(folder))
    rows = ledger.load(work)["rows"]
    out = []
    for d, dirs, files in os.walk(folder):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            if f.startswith("."):
                continue
            p = os.path.join(d, f)
            text, note = text_of(p)
            rec = {"file": os.path.relpath(p, folder), "vendor": "", "date": "", "total": "", "status": note, "ids": "", "ledger": ""}
            if text:
                rd, tot = find_date(text), find_total(text)
                rec["vendor"], rec["date"] = vendor(text), rd.isoformat() if rd else ""
                if tot is None:
                    rec["status"] = "no total read"
                else:
                    rec["total"] = "%.2f" % tot
                    got = fits(rd, tot, rows, before, after)
                    rec["ids"] = " ".join(r["id"] for r in got)
                    rec["ledger"] = " | ".join("%s %s %s" % (r["date"], ledger.mask(r["acct"]), r["desc"][:50]) for r in got)
                    if not got:
                        rec["status"] = "no ledger line for this amount in the window"
                    elif rd is None:
                        rec["status"] = "no date read; %d ledger line%s for this amount" % (len(got), "" if len(got) == 1 else "s")
                    elif len(got) == 1:
                        rec["status"] = "paired"
                    else:
                        rec["status"] = "%d ledger lines fit" % len(got)
            out.append(rec)
    cols = ["file", "vendor", "date", "total", "status", "ids", "ledger"]
    with open(os.path.join(work, "receipts.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    paired = sum(1 for r in out if r["status"] == "paired")
    W = ["RECEIPTS", "Folder: %s" % folder,
         "%s. %d paired with one ledger line. Window: %d days before the receipt's date to %d days after." % (
             ledger.count(len(out), "file"), paired, before, after), ""]
    for r in out:
        W.append("%s — %s" % (r["file"], r["status"]))
        if r["vendor"] or r["total"]:
            W.append("    %s   %s   %s" % (r["vendor"], r["date"] or "no date read", ledger.money(float(r["total"])) if r["total"] else ""))
        if r["ledger"]:
            W.append("    ledger: %s" % r["ledger"])
    text = "\n".join(W) + "\n"
    with open(os.path.join(work, "receipts.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    searchlog.add(work, "receipts paired", folder, {"files": len(out), "paired": paired,
                                                    "not_paired": [r["file"] + ": " + r["status"] for r in out if r["status"] != "paired"]})
    log(text)
    return out
