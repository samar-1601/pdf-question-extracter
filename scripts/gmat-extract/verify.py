#!/usr/bin/env python3
"""Verifier for extracted GMAT JSONL.

Round-trips every extracted string against the source PDF, cross-checks
answers + stems between §4.5 and §4.6, asserts difficulty-band counts,
and rejects any field containing footer noise. Hard fails (exit 1) on R1-R10;
soft warnings logged.

Each hard failure is written to <output>/failures/ as a self-contained
fixture-ready JSON record so it can be promoted into a regression test.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from extract import pdftotext
from parsers.common import ANCHORS, LineRefMiss, normalize_for_match, rewrite_line_refs


FOOTER_NEEDLE = "To register for the GMAT"


def _strip_page_artifacts(text: str) -> str:
    """Remove pdftotext page-break noise (ebook converter URLs, date stamps,
    'To register for the GMAT' footers) before building the haystack. Without
    this, paragraphs that span a page break end up with these artifacts spliced
    in the middle and won't match verbatim."""
    out: list[str] = []
    for line in text.splitlines():
        if ANCHORS["footer"].match(line):
            continue
        if ANCHORS["page_artifact"].match(line):
            continue
        out.append(line)
    return "\n".join(out)


def _normalize_haystack(text: str) -> str:
    return normalize_for_match(text)


def _contains(haystack: str, needle: str) -> bool:
    return needle in haystack


def _closest_window(haystack: str, needle: str, ctx: int = 60) -> str:
    if not needle:
        return ""
    head = needle[: min(20, len(needle))]
    pos = haystack.find(head)
    if pos < 0:
        return ""
    start = max(0, pos - ctx)
    end = min(len(haystack), pos + len(needle) + ctx)
    return haystack[start:end]


class Report:
    def __init__(self) -> None:
        self.failures: list[dict] = []
        self.warnings: list[dict] = []
        self.rules_with_failures: set[str] = set()

    def fail(self, rule: str, **info) -> None:
        self.failures.append({"rule": rule, **info})
        self.rules_with_failures.add(rule)

    def warn(self, code: str, **info) -> None:
        self.warnings.append({"code": code, **info})


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify(
    questions: list[dict],
    passages: list[dict],
    questions_haystack: str,
    explanations_haystack: str,
    questions_haystack_no_markers: str,
    report: Report,
) -> None:
    by_pid = {p["id"]: p for p in passages}

    for q in questions:
        rule_check_field(
            report, "R1", q, "question_text_verbatim",
            q["question_text_verbatim"], questions_haystack,
        )

        for letter, choice in q["choices"].items():
            rule_check_field(
                report, "R2", q, f"choices.{letter}", choice, questions_haystack
            )

        rule_check_field(
            report, "R4", q, "explanation.summary", q["explanation"]["summary"],
            explanations_haystack,
        )
        for letter in "ABCDE":
            text = q["explanation"].get(letter, "")
            if text:
                rule_check_field(
                    report, "R4", q, f"explanation.{letter}", text, explanations_haystack
                )

        rule_check_rewriter(report, q, by_pid.get(q["passage_id"]))
        rule_check_schema(report, q)
        rule_check_footer_noise(report, q)

    for p in passages:
        for i, para in enumerate(p["paragraphs"]):
            rule_check_field(
                report, "R3", {"id": p["id"]}, f"paragraphs[{i}]", para,
                questions_haystack_no_markers,
            )
        if len(p["paragraphs"]) < 2:
            report.warn("short_passage", id=p["id"], n_paragraphs=len(p["paragraphs"]))

    rule_check_counts(report, questions, questions_haystack)


def rule_check_field(
    report: Report, rule: str, owner: dict, field: str, value: str, haystack: str
) -> None:
    needle = _normalize_haystack(value)
    if not needle:
        return
    if not _contains(haystack, needle):
        report.fail(
            rule,
            id=owner.get("id"),
            field=field,
            actual=value,
            closest_window=_closest_window(haystack, needle),
        )


def rule_check_rewriter(report: Report, q: dict, passage: dict | None) -> None:
    if passage is None:
        report.fail("R5", id=q["id"], reason="passage_id not found", passage_id=q["passage_id"])
        return
    line_map = {int(k): v for k, v in passage["line_to_paragraph"].items()}
    try:
        recomputed = rewrite_line_refs(q["question_text_verbatim"], line_map)
    except LineRefMiss as e:
        report.fail("R5", id=q["id"], reason="line_ref_miss", detail=str(e))
        return
    if q.get("roman_options"):
        block = "\n".join(f"{it['label']}. {it['text']}" for it in q["roman_options"])
        recomputed = f"{recomputed}\n\n{block}"
    if recomputed != q["question_text"]:
        report.fail(
            "R5",
            id=q["id"],
            field="question_text",
            actual=q["question_text"],
            recomputed=recomputed,
        )


def rule_check_schema(report: Report, q: dict) -> None:
    required = ["id", "passage_id", "position_in_passage", "question_text",
                "question_text_verbatim", "choices", "correct_answer",
                "explanation", "tags", "source"]
    missing = [f for f in required if f not in q or q[f] in ("", None)]
    if missing:
        report.fail("R10", id=q.get("id"), missing=missing)
        return
    if q["correct_answer"] not in "ABCDE":
        report.fail("R10", id=q["id"], reason="bad_letter", letter=q["correct_answer"])
    explanation = q["explanation"]
    for k in ("summary", "A", "B", "C", "D", "E"):
        if k not in explanation:
            report.fail("R10", id=q["id"], reason="explanation_missing", key=k)


def rule_check_footer_noise(report: Report, q: dict) -> None:
    fields = [
        ("question_text", q["question_text"]),
        ("question_text_verbatim", q["question_text_verbatim"]),
        *((f"choices.{k}", v) for k, v in q["choices"].items()),
        ("explanation.summary", q["explanation"]["summary"]),
        *((f"explanation.{k}", q["explanation"].get(k, "")) for k in "ABCDE"),
    ]
    for name, val in fields:
        if FOOTER_NEEDLE in val:
            report.fail("R9", id=q["id"], field=name, snippet=val[:120])


_DIFFICULTY_BANNER = re.compile(
    r"Questions?\s+(\d+)\s+to\s+(\d+)\s+[—–-]\s+Difficulty:\s+(Easy|Medium|Hard)"
)


def _scope_to_section_4_4(haystack: str) -> str:
    """Scope a normalized haystack to the §4.4 (RC practice questions) region.

    The full pdftotext output contains §4.4-§4.9 headers in the table of contents
    and CR sections (§4.7/§4.9) that include their own difficulty banners. We pin
    to the LAST `4.4 Practice Questions: Reading Comprehension` occurrence (which
    is the real section start, not a TOC echo) and stop at the first `4.5 Answer
    Key: Reading Comprehension` after it.
    """
    start_marker = "4.4 Practice Questions: Reading Comprehension"
    end_marker = "4.5 Answer Key: Reading Comprehension"
    start = haystack.rfind(start_marker)
    if start < 0:
        return haystack
    end = haystack.find(end_marker, start)
    return haystack[start:end] if end > 0 else haystack[start:]


def rule_check_counts(report: Report, questions: list[dict], haystack: str) -> None:
    section_text = _scope_to_section_4_4(haystack)
    expected = {}
    for m in _DIFFICULTY_BANNER.finditer(section_text):
        a, b, level = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        expected[level] = expected.get(level, 0) + (b - a + 1)

    actual: dict[str, int] = {}
    for q in questions:
        for tag in q["tags"]:
            if tag in ("easy", "medium", "hard"):
                actual[tag] = actual.get(tag, 0) + 1
                break

    for level, want in expected.items():
        got = actual.get(level, 0)
        if got != want:
            report.fail("R6", level=level, expected=want, actual=got)


def cross_check_answers_and_stems(
    questions: list[dict], explanations_text: str, report: Report
) -> None:
    """R7 (answer cross-check) + R8 (stem cross-check) by re-parsing §4.6 text."""
    from parsers.rc_explanations import parse as parse_explanations

    parsed = parse_explanations(explanations_text)
    by_n = {ex.global_number: ex for ex in parsed}

    for q in questions:
        n = q.get("book_question_number")
        if n is None:
            continue
        ex = by_n.get(n)
        if ex is None:
            report.fail("R8", id=q["id"], book_question_number=n,
                        reason="no_§4.6_explanation_for_question")
            continue
        if normalize_for_match(q["question_text_verbatim"]) != normalize_for_match(ex.stem_original):
            report.fail(
                "R8", id=q["id"], book_question_number=n,
                stem_44=q["question_text_verbatim"], stem_46=ex.stem_original,
            )
        if q["correct_answer"] != ex.correct_letter:
            report.fail(
                "R7", id=q["id"], book_question_number=n,
                answer_key=q["correct_answer"], explanation_letter=ex.correct_letter,
            )


def write_failures(failures: list[dict], out_dir: Path) -> None:
    fdir = out_dir / "failures"
    fdir.mkdir(parents=True, exist_ok=True)
    for old in fdir.glob("*.json"):
        old.unlink()
    counts: dict[str, int] = {}
    for f in failures:
        rule = f["rule"]
        counts[rule] = counts.get(rule, 0) + 1
        idx = counts[rule]
        slug = f.get("id") or f.get("level") or f.get("global_number") or f"n{idx}"
        path = fdir / f"{rule}_{idx:03d}_{slug}.json"
        path.write_text(json.dumps(f, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)

    questions = load_jsonl(args.output / "questions.jsonl")
    passages = load_jsonl(args.output / "passages.jsonl")

    cache_dir = args.output / "_extract_text"
    if (cache_dir / "questions.txt").exists():
        questions_text = (cache_dir / "questions.txt").read_text()
        explanations_text = (cache_dir / "explanations.txt").read_text()
    else:
        raise SystemExit(
            "no cached pdftotext output found — re-run extract.py first "
            f"(expected {cache_dir}/questions.txt)"
        )

    questions_text_clean = _strip_page_artifacts(questions_text)
    explanations_text_clean = _strip_page_artifacts(explanations_text)
    questions_haystack = normalize_for_match(questions_text_clean)
    explanations_haystack = normalize_for_match(explanations_text_clean)
    questions_text_no_markers = "\n".join(
        re.sub(r"^\s*\(\d+\)\s*", "", line) for line in questions_text_clean.splitlines()
    )
    questions_haystack_no_markers = normalize_for_match(questions_text_no_markers)

    report = Report()
    verify(questions, passages, questions_haystack, explanations_haystack,
           questions_haystack_no_markers, report)
    cross_check_answers_and_stems(questions, explanations_text, report)

    summary = {
        "hard_failures": len(report.failures),
        "soft_warnings": len(report.warnings),
        "rules_with_failures": sorted(report.rules_with_failures),
        "failure_counts_by_rule": {
            r: sum(1 for f in report.failures if f["rule"] == r)
            for r in sorted(report.rules_with_failures)
        },
    }
    report_path = args.output / "verify-report.json"
    report_path.write_text(
        json.dumps({"summary": summary, "failures": report.failures, "warnings": report.warnings},
                   indent=2, ensure_ascii=False)
    )

    fdir = args.output / "failures"
    if fdir.exists():
        for old in fdir.glob("*.json"):
            old.unlink()
    if report.failures:
        write_failures(report.failures, args.output)
    elif fdir.exists() and not any(fdir.iterdir()):
        fdir.rmdir()

    print(json.dumps(summary, indent=2))
    print(f"[verify] full report → {report_path}", file=sys.stderr)
    if report.failures:
        print(f"[verify] failure fixtures → {args.output/'failures'}/", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
