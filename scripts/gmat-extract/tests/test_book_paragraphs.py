"""Golden test: every passage's paragraph structure must match the printed
book exactly.

The golden file under fixtures/book_paragraphs/<source-tag>.yaml has one entry
per passage. Each entry pins:
- paragraph_count
- per-paragraph first 50 characters and last 50 characters

If the parser produces different paragraph splits for any passage, this test
fails with a diff per passage. Either:
- the parser is wrong → fix it (and add a focused fixture+test under
  tests/fixtures/passage_*.txt and tests/test_parsers.py for the case);
- the golden is wrong → fix the golden YAML to reflect the printed book.

Entries marked `needs_review: true` are auto-bootstrapped values that have NOT
yet been confirmed against the printed PDF. The test enforces them anyway —
the flag is informational, marking which entries the user must visually verify
in the visualiser before treating them as authoritative.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPO = ROOT.parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "book_paragraphs"


def _parse_yaml(text: str) -> list[dict]:
    """Tiny YAML-subset parser for our golden file format."""
    out: list[dict] = []
    cur: dict | None = None
    cur_paragraphs: list[dict] | None = None
    cur_para_entry: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- passage_index_in_book:"):
            if cur is not None:
                if cur_paragraphs is not None and cur_para_entry is not None:
                    cur_paragraphs.append(cur_para_entry)
                if cur_paragraphs is not None:
                    cur["paragraphs"] = cur_paragraphs
                out.append(cur)
            cur = {"passage_index_in_book": int(line.split(":", 1)[1].strip())}
            cur_paragraphs = None
            cur_para_entry = None
            continue
        if cur is None:
            continue
        m_kv = re.match(r"^  ([a-z_]+):\s*(.*)$", line)
        if m_kv:
            key, val = m_kv.group(1), m_kv.group(2)
            if key == "paragraphs":
                if cur_paragraphs is not None and cur_para_entry is not None:
                    cur_paragraphs.append(cur_para_entry)
                cur["paragraphs"] = cur_paragraphs or []
                cur_paragraphs = []
                cur_para_entry = None
                continue
            if key == "needs_review":
                cur["needs_review"] = val.startswith("true")
            elif key == "paragraph_count":
                cur["paragraph_count"] = int(val)
            else:
                cur[key] = val.strip()
            continue
        m_first = re.match(r"^    - first_50:\s*(.*)$", line)
        if m_first:
            if cur_para_entry is not None:
                assert cur_paragraphs is not None
                cur_paragraphs.append(cur_para_entry)
            cur_para_entry = {"first_50": _unquote(m_first.group(1))}
            continue
        m_last = re.match(r"^      last_50:\s*(.*)$", line)
        if m_last and cur_para_entry is not None:
            cur_para_entry["last_50"] = _unquote(m_last.group(1))
            continue
    if cur is not None:
        if cur_paragraphs is not None and cur_para_entry is not None:
            cur_paragraphs.append(cur_para_entry)
        if cur_paragraphs is not None:
            cur["paragraphs"] = cur_paragraphs
        out.append(cur)
    return out


def _unquote(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _normalize(s: str) -> str:
    return s.replace("\n", " ").strip()


@pytest.mark.parametrize("source_tag", ["ogvr-24-25", "ogvr-25-26"])
def test_book_paragraphs_match_golden(source_tag):
    golden_path = FIXTURES / f"{source_tag}.yaml"
    data_path = REPO / "data" / source_tag / "passages.jsonl"
    if not data_path.exists():
        pytest.skip(f"{data_path} not generated yet — run extract.py first")
    golden = _parse_yaml(golden_path.read_text())
    passages = [json.loads(l) for l in data_path.open()]
    by_idx = {p["sources"][0]["passage_index_in_book"]: p for p in passages}

    failures: list[str] = []
    for expected in golden:
        idx = expected["passage_index_in_book"]
        actual = by_idx.get(idx)
        if actual is None:
            failures.append(f"passage_index_in_book={idx}: missing from extraction")
            continue
        # Paragraph count
        if len(actual["paragraphs"]) != expected["paragraph_count"]:
            failures.append(
                f"passage_index_in_book={idx} ({actual['id']}): "
                f"paragraph_count expected={expected['paragraph_count']} "
                f"got={len(actual['paragraphs'])}"
            )
            continue
        # Per-paragraph first/last 50
        for i, exp_para in enumerate(expected.get("paragraphs", [])):
            got = _normalize(actual["paragraphs"][i])
            if not got.startswith(exp_para["first_50"]):
                failures.append(
                    f"passage_index_in_book={idx} ({actual['id']}) "
                    f"para{i+1} START mismatch:\n"
                    f"  expected: {exp_para['first_50']!r}\n"
                    f"  got     : {got[:60]!r}"
                )
            if not got.endswith(exp_para["last_50"]):
                failures.append(
                    f"passage_index_in_book={idx} ({actual['id']}) "
                    f"para{i+1} END mismatch:\n"
                    f"  expected: {exp_para['last_50']!r}\n"
                    f"  got     : {got[-60:]!r}"
                )

    if failures:
        pytest.fail(
            f"{len(failures)} golden mismatches in {source_tag}:\n\n"
            + "\n\n".join(failures[:20])
            + (f"\n\n...and {len(failures) - 20} more" if len(failures) > 20 else "")
        )


def test_no_passages_marked_needs_review_in_24_25_after_user_confirms():
    """Once the user confirms which 24-25 short passages are genuinely
    1-paragraph and removes the needs_review markers from the YAML, this test
    will run green. Until then it's expected to xfail."""
    golden = _parse_yaml((FIXTURES / "ogvr-24-25.yaml").read_text())
    pending = [g for g in golden if g.get("needs_review")]
    if pending:
        pytest.xfail(
            f"{len(pending)} passages still flagged needs_review in ogvr-24-25 — "
            "user must verify in the visualiser, then remove the flag"
        )


def test_no_passages_marked_needs_review_in_25_26_after_user_confirms():
    golden = _parse_yaml((FIXTURES / "ogvr-25-26.yaml").read_text())
    pending = [g for g in golden if g.get("needs_review")]
    if pending:
        pytest.xfail(
            f"{len(pending)} passages still flagged needs_review in ogvr-25-26 — "
            "user must verify in the visualiser, then remove the flag"
        )
