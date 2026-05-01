#!/usr/bin/env python3
"""Bootstrap the per-book paragraph golden YAML from current parser output.

For each passage in data/<source-tag>/passages.jsonl, record:
- passage_index_in_book
- passage_id
- paragraph_count
- per-paragraph {first_50, last_50}
- needs_review flag for 1-paragraph passages (since those are the most likely
  to be wrong — either genuinely short or a missed paragraph break).

After running, manually verify any `needs_review: true` entries against the
printed PDF and either:
- flip needs_review to false (it's genuinely short), or
- correct paragraph_count + paragraphs to match the book (then the golden
  test will fail and force a parser fix).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent  # repo root
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "book_paragraphs"


def first_n(text: str, n: int) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n]


def last_n(text: str, n: int) -> str:
    text = text.replace("\n", " ").strip()
    return text[-n:]


def yaml_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(source_tag: str) -> str:
    path = ROOT / "data" / source_tag / "passages.jsonl"
    passages = [json.loads(line) for line in path.open()]
    passages.sort(key=lambda r: r["sources"][0]["passage_index_in_book"])
    lines = [f"# Auto-bootstrapped from data/{source_tag}/passages.jsonl",
             f"# Each `needs_review: true` entry must be verified against the printed PDF",
             f"# before this golden becomes authoritative.",
             ""]
    for r in passages:
        idx = r["sources"][0]["passage_index_in_book"]
        npara = len(r["paragraphs"])
        lines.append(f"- passage_index_in_book: {idx}")
        lines.append(f"  passage_id: {r['id']}")
        lines.append(f"  paragraph_count: {npara}")
        if npara <= 1:
            lines.append("  needs_review: true  # 1-paragraph — verify against printed PDF")
        lines.append("  paragraphs:")
        for p in r["paragraphs"]:
            lines.append(f"    - first_50: {yaml_quote(first_n(p, 50))}")
            lines.append(f"      last_50: {yaml_quote(last_n(p, 50))}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for tag in ("ogvr-24-25", "ogvr-25-26"):
        out = FIXTURES / f"{tag}.yaml"
        out.write_text(build(tag))
        print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
