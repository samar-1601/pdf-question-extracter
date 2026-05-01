#!/usr/bin/env python3
"""GMAT OG → JSONL extractor (RC v1).

Pipeline: pdftotext per sub-section → §4.4/§4.5/§4.6 parsers → joiner → JSONL.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from parsers import rc_answer_key, rc_explanations, rc_questions
from parsers.common import (
    ANCHORS,
    LineRefMiss,
    passage_id,
    question_id,
    rewrite_line_refs,
    slugify_category,
)


def parse_range(s: str) -> tuple[int, int]:
    a, b = s.split("-", 1)
    return int(a), int(b)


def pdf_page_count(pdf: Path) -> int:
    """Return total page count via `pdfinfo` (ships with poppler alongside pdftotext)."""
    exe = shutil.which("pdfinfo") or "/opt/homebrew/bin/pdfinfo"
    if not Path(exe).exists():
        raise SystemExit("pdfinfo not installed. Install poppler: `brew install poppler`")
    out = subprocess.run(
        [exe, str(pdf)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise SystemExit(f"could not determine page count of {pdf}")


def pdftotext(pdf: Path, start: int, end: int) -> str:
    exe = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    if not Path(exe).exists():
        raise SystemExit("pdftotext not installed. Install poppler: `brew install poppler`")
    out = subprocess.run(
        [exe, "-layout", "-f", str(start), "-l", str(end), "-eol", "unix", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def _embed_roman_items(stem: str, items: list[dict[str, str]] | None) -> str:
    if not items:
        return stem
    block = "\n".join(f"{it['label']}. {it['text']}" for it in items)
    return f"{stem}\n\n{block}"


def join(
    raw_passages: list[rc_questions.RawPassage],
    raw_questions: list[rc_questions.RawQuestion],
    answer_key: dict[int, str],
    explanations: list[rc_explanations.RawExplanation],
    source_tag: str,
) -> tuple[list[dict], list[dict]]:
    explanations_by_n = {e.global_number: e for e in explanations}

    passages_out: list[dict] = []
    passage_id_for_index: dict[int, str] = {}

    for idx, p in enumerate(raw_passages):
        text = " ".join(p.paragraphs)
        pid = passage_id(text)
        passage_id_for_index[idx] = pid
        record = {
            "id": pid,
            "difficulty": p.difficulty or None,
            "paragraphs": p.paragraphs,
            "intro_note": p.intro_note,
            "line_to_paragraph": {str(k): v for k, v in sorted(p.line_to_paragraph.items())},
            "tags": [source_tag, p.difficulty] if p.difficulty else [source_tag],
            "sources": [
                {
                    "book": source_tag,
                    "page": p.page,
                    "passage_index_in_book": p.passage_index_in_book,
                }
            ],
        }
        passages_out.append(record)

    grouped = defaultdict(list)
    for q in raw_questions:
        grouped[q.passage_index].append(q)

    questions_out: list[dict] = []
    for passage_idx, qs in grouped.items():
        if passage_idx < 0 or passage_idx >= len(raw_passages):
            raise ValueError(f"question references missing passage index {passage_idx}")
        pid = passage_id_for_index[passage_idx]
        line_map = {int(k): v for k, v in passages_out[passage_idx]["line_to_paragraph"].items()}

        for n_in_passage, q in enumerate(sorted(qs, key=lambda r: r.global_number), start=1):
            try:
                stem_rewritten = rewrite_line_refs(q.stem_original, line_map)
            except LineRefMiss as e:
                raise SystemExit(f"line-ref miss in question {q.global_number}: {e}")

            ans = answer_key.get(q.global_number)
            if ans is None:
                raise SystemExit(f"answer key missing question {q.global_number}")

            ex = explanations_by_n.get(q.global_number)
            if ex is None:
                raise SystemExit(f"explanation missing for question {q.global_number}")

            tags = [source_tag, "reading_comprehension", q.difficulty]
            if ex.category:
                tags.append(slugify_category(ex.category))

            record = {
                "id": question_id(pid, n_in_passage),
                "passage_id": pid,
                "position_in_passage": n_in_passage,
                "book_question_number": q.global_number,
                "difficulty": q.difficulty,
                "question_text": _embed_roman_items(stem_rewritten, q.stem_items),
                "question_text_verbatim": q.stem_original,
                "roman_options": q.stem_items,
                "choices": q.choices,
                "correct_answer": ans,
                "explanation": {
                    "summary": ex.overall,
                    **{letter: ex.per_choice.get(letter, "") for letter in "ABCDE"},
                },
                "tags": tags,
                "source": {"book": source_tag, "page": q.page},
            }
            questions_out.append(record)

    return passages_out, questions_out


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


_STANDARD_TAGS = {
    "reading_comprehension",
    "easy", "medium", "hard",
}


def _question_type_from_tags(tags: list[str], source_tag: str) -> str | None:
    """Recover the un-slugified RC category label (e.g. 'Supporting Idea')
    from the slugged tag list. The category is the only tag that isn't
    standard or the source-tag."""
    for t in tags:
        if t in _STANDARD_TAGS or t == source_tag:
            continue
        return " ".join(w.capitalize() for w in t.split("_"))
    return None


def passage_blocks(
    passages_out: list[dict],
    questions_out: list[dict],
    source_tag: str,
) -> list[dict]:
    """Combine the per-passage passage record + its questions into the
    downstream-friendly shape. Every original field is preserved; the
    sample-shape names (passage_id int, passage_paragraphs, number, options,
    question_type, rationale, option_explanations) are added on top."""
    by_pid: dict[str, list[dict]] = {}
    for q in questions_out:
        by_pid.setdefault(q["passage_id"], []).append(q)

    blocks: list[dict] = []
    for p in passages_out:
        qs = sorted(
            by_pid.get(p["id"], []),
            key=lambda r: r["book_question_number"],
        )
        new_qs = []
        for q in qs:
            ex = q.get("explanation", {}) or {}
            new_qs.append({
                # sample-shape:
                "number": q["book_question_number"],
                "question_text": q["question_text"],
                "options": q["choices"],
                "question_type": _question_type_from_tags(
                    q.get("tags", []), source_tag
                ),
                "rationale": ex.get("summary", ""),
                "option_explanations": {
                    letter: ex.get(letter, "") for letter in "ABCDE"
                },
                "correct_answer": q["correct_answer"],
                # extras (kept):
                "id": q["id"],
                "position_in_passage": q["position_in_passage"],
                "difficulty": q.get("difficulty"),
                "question_text_verbatim": q["question_text_verbatim"],
                "roman_options": q.get("roman_options"),
                "tags": q.get("tags", []),
                "source": q.get("source"),
            })

        blocks.append({
            # sample-shape:
            "passage_id": p["sources"][0]["passage_index_in_book"],
            "passage_paragraphs": p["paragraphs"],
            "questions": new_qs,
            # extras (kept):
            "id": p["id"],
            "difficulty": p.get("difficulty"),
            "intro_note": p.get("intro_note"),
            "line_to_paragraph": p.get("line_to_paragraph", {}),
            "tags": p.get("tags", []),
            "sources": p.get("sources", []),
            "book_tag": source_tag,
        })

    return blocks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--source-tag", required=True)
    ap.add_argument(
        "--questions-pages",
        default=None,
        help="Page range for §4.4 questions, e.g. '94-227'. Defaults to the full PDF.",
    )
    ap.add_argument(
        "--answer-key-pages",
        default=None,
        help="Page range for §4.5 answer key. Defaults to the full PDF.",
    )
    ap.add_argument(
        "--explanations-pages",
        default=None,
        help="Page range for §4.6 explanations. Defaults to the full PDF.",
    )
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    full_range_cached: str | None = None

    def resolve(arg_value: str | None, label: str) -> tuple[int, int]:
        nonlocal full_range_cached
        if arg_value is not None:
            return parse_range(arg_value)
        if full_range_cached is None:
            full_range_cached = f"1-{pdf_page_count(args.pdf)}"
            print(
                f"[extract] no explicit range — defaulting all unspecified "
                f"sections to full PDF ({full_range_cached})",
                file=sys.stderr,
            )
        print(f"[extract] {label}: using default {full_range_cached}", file=sys.stderr)
        return parse_range(full_range_cached)

    q_start, q_end = resolve(args.questions_pages, "--questions-pages")
    a_start, a_end = resolve(args.answer_key_pages, "--answer-key-pages")
    e_start, e_end = resolve(args.explanations_pages, "--explanations-pages")

    print(f"[extract] §4.4 pdftotext pp.{q_start}-{q_end}", file=sys.stderr)
    questions_text = pdftotext(args.pdf, q_start, q_end)
    print(f"[extract] §4.5 pdftotext pp.{a_start}-{a_end}", file=sys.stderr)
    answers_text = pdftotext(args.pdf, a_start, a_end)
    print(f"[extract] §4.6 pdftotext pp.{e_start}-{e_end}", file=sys.stderr)
    explanations_text = pdftotext(args.pdf, e_start, e_end)

    raw_passages, raw_questions = rc_questions.parse(questions_text, page_offset=q_start)
    answer_key = rc_answer_key.parse(answers_text)
    explanations = rc_explanations.parse(explanations_text, page_offset=e_start)

    print(
        f"[extract] parsed: {len(raw_passages)} passages, "
        f"{len(raw_questions)} questions, {len(answer_key)} answers, "
        f"{len(explanations)} explanations",
        file=sys.stderr,
    )

    passages_out, questions_out = join(
        raw_passages, raw_questions, answer_key, explanations, args.source_tag
    )

    args.output.mkdir(parents=True, exist_ok=True)
    write_jsonl(passages_out, args.output / "passages.jsonl")
    write_jsonl(questions_out, args.output / "questions.jsonl")
    blocks_out = passage_blocks(passages_out, questions_out, args.source_tag)
    write_jsonl(blocks_out, args.output / "passage_blocks.jsonl")
    (args.output / "_extract_text").mkdir(exist_ok=True)
    (args.output / "_extract_text" / "questions.txt").write_text(questions_text)
    (args.output / "_extract_text" / "answers.txt").write_text(answers_text)
    (args.output / "_extract_text" / "explanations.txt").write_text(explanations_text)

    print(
        f"[extract] wrote {len(passages_out)} passages → {args.output/'passages.jsonl'}\n"
        f"[extract] wrote {len(questions_out)} questions → {args.output/'questions.jsonl'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
