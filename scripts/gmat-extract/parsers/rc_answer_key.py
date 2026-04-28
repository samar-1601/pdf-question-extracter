"""Parser for §4.5 (Answer Key: Reading Comprehension).

Flat list of `<n>. <letter>` lines. Hard-fails on any unrecognized non-blank line
that isn't the section header itself.
"""
from __future__ import annotations

import re

from .common import ANCHORS

ENTRY = re.compile(r"^\s*(\d+)\.\s+([A-E])\s*$")
SECTION_HEADER = re.compile(r"^\s*4\.5\s+Answer Key:")
NEXT_SECTION_HEADER = re.compile(r"^\s*4\.6\s")


def parse(text: str) -> dict[int, str]:
    answers: dict[int, str] = {}
    in_section = False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if SECTION_HEADER.match(raw):
            in_section = True
            answers = {}
            continue
        if not in_section:
            continue
        if NEXT_SECTION_HEADER.match(raw):
            if answers:
                break
            in_section = False
            continue
        if raw.strip() == "Reading Comprehension":
            continue
        if ANCHORS["footer"].match(raw):
            continue
        if ANCHORS["page_artifact"].match(raw):
            continue
        m = ENTRY.match(raw)
        if not m:
            raise ValueError(f"Unrecognized line in §4.5: {raw!r}")
        answers[int(m.group(1))] = m.group(2)
    return answers
