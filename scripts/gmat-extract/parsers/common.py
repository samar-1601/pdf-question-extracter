"""Shared regexes, normalizers, and the line-ref rewriter."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

ANCHORS = {
    "footer": re.compile(r"^\s*To register for the GMAT"),
    "page_artifact": re.compile(
        r"^\s*(?:file:///|https?://)"
        r"|^\s*\d{1,2}/\d{1,2}/\d{4}\s*,?\s*\d{1,2}:\d{2}"
    ),
    "difficulty": re.compile(
        r"^\s*Questions?\s+(\d+)\s+to\s+(\d+)\s+[—–-]\s+Difficulty:\s+(Easy|Medium|Hard)\s*$"
    ),
    "passage_start": re.compile(r"^\s*Line(?=\s|[A-Z\"'])"),
    "line_marker": re.compile(r"^\s*\((\d+)\)\s*"),
    "passage_divider": re.compile(
        r"^\s*Questions?\s+(\d+)\s*[–—-]\s*(\d+)\s+refer\s+to\s+the\s+passage"
        r"(?:\s+on\s+page\s+(\d+))?\.?\s*$"
    ),
    "question_stem": re.compile(r"^\s*(\d+)\.\s+(\S.*)$"),
    "stem_item": re.compile(r"^\s*([IVX]+)\.\s+(\S.*)$"),
    "choice": re.compile(r"^\s*([A-E])\.\s+(\S.*)$"),
    "correct_answer_line": re.compile(r"^\s*The correct answer is ([A-E])\.\s*$"),
    "section_4_4_header": re.compile(r"^\s*4\.4\s+Practice Questions:"),
    "section_4_5_header": re.compile(r"^\s*4\.5\s+Answer Key:"),
    "section_4_6_header": re.compile(r"^\s*4\.6\s+Answer Explanations:"),
    "section_4_7_header": re.compile(r"^\s*4\.7\s+Practice Questions:"),
}


def normalize_for_match(s: str) -> str:
    """NFKC + collapse whitespace + trim. Keeps smart quotes / dashes verbatim."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_for_hash(s: str) -> str:
    """Stable de-dupe key: lowercase, collapse whitespace, canonicalize quotes."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("‘", "'").replace("’", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def passage_id(text: str) -> str:
    h = hashlib.sha1(normalize_for_hash(text).encode("utf-8")).hexdigest()
    return f"p_{h[:12]}"


def question_id(passage_id: str, number_in_passage: int) -> str:
    h = hashlib.sha1(f"{passage_id}:{number_in_passage}".encode("utf-8")).hexdigest()
    return f"q_{h[:12]}"


def slugify_category(label: str) -> str:
    s = label.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


@dataclass
class LineRefMiss(Exception):
    """Raised when a stem references a line number absent from line_to_paragraph."""
    line_no: int
    stem: str

    def __str__(self) -> str:
        return f"line {self.line_no} not found in line_to_paragraph map (stem: {self.stem!r})"


_LINE_REF_PATTERNS = [
    (re.compile(r"\blines\s+(\d+)\s*[–—-]\s*(\d+)\b"), "range"),
    (re.compile(r"\blines\s+(\d+)\s+and\s+(\d+)\b"), "range"),
    (re.compile(r"\bline\s+(\d+)\s+and\s+line\s+(\d+)\b"), "range"),
    (re.compile(r"\bline\s+(\d+)\b"), "single"),
]


def rewrite_line_refs(stem: str, line_to_paragraph: dict[int, int]) -> str:
    """Substitute 'line N' / 'lines N–M' references with paragraph references.

    Range references collapsing to one paragraph become 'paragraph N'.
    Range references spanning paragraphs become 'paragraphs N–M' (en-dash).
    """
    def lookup(n: int) -> int:
        if n not in line_to_paragraph:
            raise LineRefMiss(line_no=n, stem=stem)
        return line_to_paragraph[n]

    result = stem
    for pattern, kind in _LINE_REF_PATTERNS:
        def replace(m: re.Match[str]) -> str:
            if kind == "single":
                return f"paragraph {lookup(int(m.group(1)))}"
            a, b = lookup(int(m.group(1))), lookup(int(m.group(2)))
            return f"paragraph {a}" if a == b else f"paragraphs {a}–{b}"

        result = pattern.sub(replace, result)
    return result
