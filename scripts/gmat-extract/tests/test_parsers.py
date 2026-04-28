"""Parser tests grounded in real pdftotext output from the source PDF."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parsers import rc_answer_key, rc_explanations, rc_questions  # noqa: E402
from parsers.common import (  # noqa: E402
    LineRefMiss,
    normalize_for_match,
    passage_id,
    rewrite_line_refs,
    slugify_category,
)

FIXTURES = ROOT / "tests" / "fixtures"


def fx(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_passage_paragraph_split():
    text = fx("easy_p1_q1-4.txt")
    passages, _ = rc_questions.parse(text, page_offset=94)
    assert len(passages) == 1
    p = passages[0]
    assert len(p.paragraphs) >= 2, f"expected ≥2 paragraphs, got {len(p.paragraphs)}"
    assert p.paragraphs[0].startswith("Human beings, born with a drive to explore")
    assert any(par.startswith("To survive in the future") for par in p.paragraphs)


def test_line_to_paragraph_map():
    text = fx("easy_p1_q1-4.txt")
    passages, _ = rc_questions.parse(text, page_offset=94)
    p = passages[0]
    assert p.line_to_paragraph[1] == 1
    assert p.line_to_paragraph[5] == 1
    assert p.line_to_paragraph[15] == 2, p.line_to_paragraph
    assert p.line_to_paragraph[30] == 2


def test_question_count_and_difficulty():
    text = fx("easy_p1_q1-4.txt")
    _, questions = rc_questions.parse(text, page_offset=94)
    assert [q.global_number for q in questions] == [1, 2, 3, 4]
    assert all(q.difficulty == "easy" for q in questions)


def test_question_choices_a_to_e():
    text = fx("easy_p1_q1-4.txt")
    _, questions = rc_questions.parse(text, page_offset=94)
    q1 = questions[0]
    assert set(q1.choices.keys()) == set("ABCDE")
    assert q1.choices["C"].startswith("make important policy decisions alone")


def test_stem_verbatim_substring_of_source():
    text = fx("easy_p1_q1-4.txt")
    _, questions = rc_questions.parse(text, page_offset=94)
    haystack = normalize_for_match(text)
    for q in questions:
        assert q.stem_original in haystack, (
            f"Q{q.global_number} stem not found verbatim:\n  {q.stem_original!r}"
        )
        for letter, choice in q.choices.items():
            assert choice in haystack, (
                f"Q{q.global_number} choice {letter} not found verbatim:\n  {choice!r}"
            )


def test_no_footer_noise_in_extracted_fields():
    text = fx("easy_p1_q1-4.txt")
    passages, questions = rc_questions.parse(text, page_offset=94)
    for q in questions:
        assert "To register for the GMAT" not in q.stem_original
        for v in q.choices.values():
            assert "To register for the GMAT" not in v
    for p in passages:
        for para in p.paragraphs:
            assert "To register for the GMAT" not in para


def test_answer_key_parses_clean():
    text = fx("answer_key_head.txt")
    answers = rc_answer_key.parse(text)
    assert answers[1] == "C"
    assert answers[2] == "E"
    assert answers[8] == "C"


def test_explanations_parses_q1():
    text = fx("explanations_q1-2.txt")
    parsed = rc_explanations.parse(text, page_offset=233)
    by_n = {e.global_number: e for e in parsed}
    q1 = by_n[1]
    assert q1.correct_letter == "C"
    assert q1.category == "Supporting Idea"
    assert "contrast the passage draws" in q1.overall
    assert q1.per_choice["C"].startswith("Correct.")


def test_rewriter_single_line_to_paragraph():
    line_map = {14: 1, 19: 1, 22: 2}
    out = rewrite_line_refs(
        'the "norms" mentioned in line 19', line_map
    )
    assert out == 'the "norms" mentioned in paragraph 1'


def test_rewriter_range_within_paragraph():
    line_map = {42: 3, 50: 3}
    out = rewrite_line_refs("findings described in lines 42–50", line_map)
    assert out == "findings described in paragraph 3"


def test_rewriter_range_across_paragraphs():
    line_map = {10: 1, 20: 2}
    out = rewrite_line_refs("see lines 10-20", line_map)
    assert out == "see paragraphs 1–2"


def test_rewriter_misses_raise():
    import pytest
    with pytest.raises(LineRefMiss):
        rewrite_line_refs("see line 99", {1: 1})


def test_passage_id_stable_across_whitespace():
    a = "Human beings,  born with a drive to explore."
    b = "Human beings, born with a drive to explore."
    assert passage_id(a) == passage_id(b)


def test_passage_id_stable_across_smart_quotes():
    a = "Human beings, born with a 'drive' to explore."
    b = "Human beings, born with a 'drive' to explore."
    assert passage_id(a) == passage_id(b)


def test_slugify_category():
    assert slugify_category("Supporting Idea") == "supporting_idea"
    assert slugify_category("Style and Tone") == "style_and_tone"


def test_rc_questions_skips_toc():
    """OGVR 24-25 has all §4.4-§4.9 headers in the table of contents, before
    real content. Parser must not exit on the TOC §4.5 echo and must reach
    the real §4.4 block that follows."""
    text = fx("toc_then_real_44.txt")
    passages, questions = rc_questions.parse(text, page_offset=1)
    assert len(passages) == 1, f"expected 1 passage, got {len(passages)}"
    assert len(questions) == 1, f"expected 1 question, got {len(questions)}"
    assert questions[0].global_number == 1
    assert questions[0].difficulty == "easy"


def test_rc_answer_key_skips_toc():
    """TOC contains the §4.5 and §4.6 lines on consecutive rows; the parser must
    not treat the TOC echo as the section and exit on TOC §4.6 with 0 entries."""
    text = fx("toc_then_real_45.txt")
    answers = rc_answer_key.parse(text)
    assert answers == {1: "C", 2: "E", 3: "D", 4: "E", 5: "A"}


def test_rc_explanations_stops_at_4_7():
    """Explanations parser must stop at §4.7 (Critical Reasoning practice
    questions) — otherwise it ingests CR question stems as RC explanations."""
    text = fx("explanations_46_to_47_boundary.txt")
    parsed = rc_explanations.parse(text, page_offset=1)
    assert [e.global_number for e in parsed] == [1], (
        f"expected only Q1 from RC §4.6; got {[e.global_number for e in parsed]}"
    )
