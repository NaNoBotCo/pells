"""Chat exports: find the threads that talk about the subject, and sort them into tiers for reading.

Reads a Messenger download (message_*.json files) and text exports with one message per line
([date, time] name: words  or  date, time - name: words). A thread is taken when one of its
messages carries a subject word. Its tier is the first tier whose words appear in the thread.

    search(folder, work)   writes chats.csv, chats.txt and one text file per taken thread in chats-staged/

The word lists are in rules/chat_terms.json; a work folder's own chat_terms.json is read first.
"""
import csv
import json
import os
import re
from datetime import datetime, timezone

from . import searchlog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE_A = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),? ([^\]]+)\] ([^:]{1,60}): (.*)$")
LINE_B = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),? (\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm])?) - ([^:]{1,60}): (.*)$")


def load_terms(work=None, path=None):
    for p in (path, os.path.join(work, "chat_terms.json") if work else None, os.path.join(ROOT, "rules", "chat_terms.json")):
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                t = json.load(fh)
            t["_subject"] = [re.compile(x, re.I) for x in t["subject"]]
            for tier in t["tiers"]:
                tier["_p"] = [re.compile(x, re.I) for x in tier["patterns"]]
            t["_src"] = p
            return t
    raise SystemExit("no chat_terms.json found")


def _fix(s):
    """Messenger downloads store UTF-8 bytes as Latin-1 characters; put them back."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _mdy(s):
    m, d, y = [int(x) for x in s.split("/")]
    return "%04d-%02d-%02d" % (y + 2000 if y < 100 else y, m, d)


def threads(folder):
    """[{title, source, people, messages: [(date, sender, words)]}], messages oldest first."""
    out, groups = [], {}
    for d, dirs, files in os.walk(folder):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            p = os.path.join(d, f)
            if re.match(r"message_\d+\.json$", f):
                groups.setdefault(d, []).append(p)
            elif f.lower().endswith(".txt"):
                msgs = []
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        m = LINE_A.match(ln.strip("‎﻿ \n")) or LINE_B.match(ln.strip("‎﻿ \n"))
                        if m:
                            msgs.append((_mdy(m.group(1)), m.group(3).strip(), m.group(4)))
                        elif msgs and ln.strip():
                            msgs[-1] = (msgs[-1][0], msgs[-1][1], msgs[-1][2] + " " + ln.strip())
                if msgs:
                    out.append({"title": os.path.splitext(f)[0], "source": os.path.relpath(p, folder),
                                "people": sorted(set(m[1] for m in msgs)), "messages": msgs})
    for d in sorted(groups):
        msgs, title, people = [], os.path.basename(d), set()
        for p in sorted(groups[d]):
            try:
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (ValueError, OSError):
                continue
            title = _fix(data.get("title") or title)
            for x in data.get("participants") or []:
                people.add(_fix(x.get("name") or ""))
            for m in data.get("messages") or []:
                if not m.get("content"):
                    continue
                when = datetime.fromtimestamp((m.get("timestamp_ms") or 0) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
                msgs.append((when, _fix(m.get("sender_name") or ""), _fix(m["content"])))
        msgs.sort(key=lambda m: m[0])
        if msgs:
            out.append({"title": title, "source": os.path.relpath(d, folder), "people": sorted(people - {""}), "messages": msgs})
    return out


def search(folder, work, terms_path=None, log=print):
    folder = os.path.abspath(os.path.expanduser(folder))
    t = load_terms(work, terms_path)
    staged = os.path.join(work, "chats-staged")
    os.makedirs(staged, exist_ok=True)
    rows, all_threads = [], threads(folder)
    for th in all_threads:
        hit = [i for i, m in enumerate(th["messages"]) if any(p.search(m[2]) for p in t["_subject"])]
        if not hit:
            continue
        tier, tier_name = t["context_tier"]["tier"], t["context_tier"]["name"]
        why = set()
        for cand in t["tiers"]:
            got = [i for i, m in enumerate(th["messages"]) if any(p.search(m[2]) for p in cand["_p"])]
            if got:
                tier, tier_name, why = cand["tier"], cand["name"], set(got)
                break
        slug = re.sub(r"[^A-Za-z0-9]+", "-", th["title"]).strip("-")[:50] or "thread"
        name = "%s-%s.txt" % (tier, slug)
        with open(os.path.join(staged, name), "w", encoding="utf-8") as fh:
            fh.write("%s\nSource: %s\nPeople: %s\nTier %s: %s\nLines marked >> carry a subject word or a tier word.\n\n" % (
                th["title"], th["source"], ", ".join(th["people"]), tier, tier_name))
            for i, m in enumerate(th["messages"]):
                fh.write("%s %s  %s: %s\n" % (">>" if (i in hit or i in why) else "  ", m[0], m[1], m[2]))
        rows.append({"tier": tier, "tier_name": tier_name, "thread": th["title"], "people": ", ".join(th["people"]),
                     "first": th["messages"][0][0], "last": th["messages"][-1][0], "messages": len(th["messages"]),
                     "subject_lines": len(hit), "source": th["source"], "staged": name})
    rows.sort(key=lambda r: (r["tier"], r["first"]))
    cols = ["tier", "tier_name", "thread", "people", "first", "last", "messages", "subject_lines", "source", "staged"]
    with open(os.path.join(work, "chats.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    W = ["CHATS", "Folder: %s" % folder, "Words: %s" % t["_src"],
         "%d threads read. %d carry a subject word. %d do not." % (len(all_threads), len(rows), len(all_threads) - len(rows)),
         "A tier is a pile for reading; the staged copies are in chats-staged/.", ""]
    for r in rows:
        W.append("%s  %s  %s to %s  %d messages, %d on the subject  [%s]  %s" % (
            r["tier"], r["thread"], r["first"], r["last"], r["messages"], r["subject_lines"], r["tier_name"], r["staged"]))
    text = "\n".join(W) + "\n"
    with open(os.path.join(work, "chats.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    c = {"threads_read": len(all_threads), "threads_taken": len(rows), "threads_without_a_subject_word": len(all_threads) - len(rows)}
    for k in sorted(counts):
        c["tier_%s" % k] = counts[k]
    searchlog.add(work, "chats searched", folder, c)
    log(text)
    return rows
