"""The search log: one line for each thing read, with counts, whether or not anything turned up.

search-log.jsonl is the record; search-log.txt is the same lines for a reader.
"""
import json
import os
from datetime import datetime, timezone


def add(work, what, source, counts):
    os.makedirs(work, exist_ok=True)
    rec = {"when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "what": what, "source": source}
    rec.update(counts)
    with open(os.path.join(work, "search-log.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(os.path.join(work, "search-log.txt"), "w", encoding="utf-8") as fh:
        fh.write(render(work))
    return rec


def entries(work):
    p = os.path.join(work, "search-log.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def render(work):
    out = ["SEARCH LOG", "Times are UTC. Oldest first.", ""]
    for e in entries(work):
        out.append("%s  %s" % (e["when"], e["what"]))
        out.append("  source: %s" % e["source"])
        for k, v in e.items():
            if k in ("when", "what", "source"):
                continue
            if isinstance(v, list):
                out.append("  %s: %d" % (k.replace("_", " "), len(v)))
                out.extend("    %s" % x for x in v)
            else:
                out.append("  %s: %s" % (k.replace("_", " "), v))
        out.append("")
    return "\n".join(out)
