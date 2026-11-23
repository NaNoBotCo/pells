"""PDF pages as text, read once per file and cached under the file's SHA-256."""
import hashlib
import json
import os


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_pdfs(root):
    """PDFs under root, sorted by relative path. A single file is its own list."""
    root = os.path.expanduser(root)
    if os.path.isfile(root):
        return [root]
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            if f.lower().endswith(".pdf") and not f.startswith("."):
                out.append(os.path.join(d, f))
    return out


def read_pages(path, cache_dir=None):
    """(sha, [page text, ...]) or (sha, None) when the file does not open as a PDF."""
    h = sha256(path)
    cp = os.path.join(cache_dir, h + ".json") if cache_dir else None
    if cp and os.path.exists(cp):
        with open(cp, encoding="utf-8") as fh:
            return h, json.load(fh)
    try:
        from pypdf import PdfReader
        pages = [(pg.extract_text() or "") for pg in PdfReader(path).pages]
    except Exception:
        return h, None
    if cp:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(pages, fh)
    return h, pages


def has_text(pages):
    """False when the pages read as a scan: under 20 characters a page on average."""
    if not pages:
        return False
    return sum(len(p.strip()) for p in pages) >= 20 * len(pages)
