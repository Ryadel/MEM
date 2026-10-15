"""MEM OPTIMIZE PAGES: which knowledge base pages weigh most on sessions, and what maintenance would lighten them.

Reads a mem-stats REPORT (JSON, from --report or stdin) and its `kb_pages` section: per page, the tokens it added
when read (`new`) and the tokens every later request re-sent while it stayed in context (`carried`). A page is
listed when it carried at least --min-carried tokens and is still at least --min-size tokens long (characters/4).
The suggestion depends on the kind of page. Read-only: it never edits a page — rewriting the knowledge base
automatically would trade its accuracy for tokens; the user decides.

Pages recorded by Claude Code only: the Codex adapter does not measure KB pages yet.

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

SUGGESTIONS = (
    ("tasks/current/", "move concluded history (done phases, superseded measurements, resolved notes) to a page under "
                       "tasks/done/ or a linked history page; keep status, decisions, open items and the next step"),
    ("logs/", "the latest log is read every session: keep the resume point short and move details to the task pages "
              "it names"),
    ("drafts/", "once accepted, fold what was decided into the ADR and archive the draft"),
    ("decisions/", "keep the decision and its reasons; move long measurements or alternatives to a linked reference"),
    ("MEM.index.md", "keep one short line per page; details belong in the pages themselves"),
)
SPECIAL = {
    "<shell>": "knowledge base read through shell commands: since MEM 1.2.0 pages are read with the file-reading "
               "tool; check for instructions or habits that still use cat/type/Get-Content",
    "<search>": "searches inside the knowledge base: normal; heavy only if searches return whole files",
    "<instructions>": "the MEM pointer in the client's instruction file, carried by every request: keep it to a few "
                      "lines",
}


def suggestion(page):
    for prefix, text in SUGGESTIONS:
        if page.startswith(prefix) or page == prefix:
            return text
    return "consider splitting it by topic, so that a request reads only the part it needs"


def review(report, kb_root, min_carried, min_size, top):
    pages = (report.get("kb_pages") or {}).get("all") or {}
    if not pages:  # older reports keep only the ranked top
        pages = {e["page"]: e for e in (report.get("kb_pages") or {}).get("top") or []}
    found, notes, gone = [], [], []
    for page, value in sorted(pages.items(), key=lambda kv: -kv[1].get("carried", 0)):
        carried = value.get("carried", 0)
        if carried < min_carried:
            continue
        if page in SPECIAL:
            notes.append({"page": page, "carried_tokens": carried, "note": SPECIAL[page]})
            continue
        path = kb_root / page
        if not path.is_file():
            gone.append(page)
            continue
        size = math.ceil(len(path.read_text(encoding="utf-8", errors="replace")) / 4)
        if size >= min_size:
            found.append({"page": page, "carried_tokens": carried, "read_tokens": value.get("new", 0),
                          "size_tokens_now": size, "suggestion": suggestion(page)})
    return {"period": report.get("period"), "pages": found[:top], "notes": notes, "no_longer_present": gone,
            "meaning": "carried = tokens re-sent by later requests while the page stayed in context; read = tokens "
                       "added when it was read; size now = characters/4. Suggestions only: nothing is changed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", type=Path, help="mem-stats REPORT JSON (default: stdin)")
    parser.add_argument("--kb-root", type=Path, required=True)
    parser.add_argument("--min-carried", type=int, default=500_000, help="tokens carried to be listed")
    parser.add_argument("--min-size", type=int, default=4_000, help="current size, in tokens, to be listed")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    source = args.report.read_text(encoding="utf-8-sig") if args.report else sys.stdin.read()
    result = review(json.loads(source), args.kb_root, args.min_carried, args.min_size, args.top)
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
