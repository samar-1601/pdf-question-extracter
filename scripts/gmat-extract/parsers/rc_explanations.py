"""Parser for §4.6 (Answer Explanations: Reading Comprehension).

Each question block:
  <stem>
  <choices A-E>
  <Category Label>            (single line, e.g. "Supporting Idea")
  <overall explanation paragraph(s)>
  A. <per-choice explanation>
  B. ...
  C. Correct. ...   (correct one is prefixed with literal "Correct.")
  D. ...
  E. ...
  The correct answer is X.    (terminator)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .common import ANCHORS, normalize_for_match

KNOWN_CATEGORIES = {
    "Supporting Idea", "Inference", "Application", "Main Idea", "Evaluation",
    "Function", "Logical Structure", "Style and Tone", "Style", "Tone",
    "Logical Function",
}


@dataclass
class RawExplanation:
    global_number: int
    stem_original: str
    stem_items: list[dict[str, str]] | None
    choices: dict[str, str]
    category: str | None
    overall: str
    per_choice: dict[str, str]
    correct_letter: str
    page: int


@dataclass
class _Builder:
    global_number: int
    page: int
    stem_lines: list[str] = field(default_factory=list)
    stem_items: list[dict[str, str]] = field(default_factory=list)
    current_stem_item: dict[str, list[str]] | None = None
    choices: dict[str, list[str]] = field(default_factory=dict)
    current_choice: str | None = None
    category_lines: list[str] = field(default_factory=list)
    overall_lines: list[str] = field(default_factory=list)
    per_choice: dict[str, list[str]] = field(default_factory=dict)
    current_per_choice: str | None = None
    state: str = "STEM"
    correct_letter: str | None = None

    def finalize_stem_item(self) -> None:
        if self.current_stem_item is not None:
            self.stem_items.append(
                {"label": self.current_stem_item["label"],
                 "text": " ".join(self.current_stem_item["text"])}
            )
            self.current_stem_item = None

    def to_raw(self) -> RawExplanation:
        self.finalize_stem_item()
        return RawExplanation(
            global_number=self.global_number,
            stem_original=normalize_for_match(" ".join(self.stem_lines)),
            stem_items=self.stem_items or None,
            choices={k: normalize_for_match(" ".join(v)) for k, v in self.choices.items()},
            category=" ".join(self.category_lines).strip() or None,
            overall=normalize_for_match(" ".join(self.overall_lines)),
            per_choice={k: normalize_for_match(" ".join(v)) for k, v in self.per_choice.items()},
            correct_letter=self.correct_letter or "",
            page=self.page,
        )


def parse(text: str, page_offset: int = 1) -> list[RawExplanation]:
    out: list[RawExplanation] = []
    builder: _Builder | None = None
    seen_choice_in_question = False
    current_page = page_offset
    section_state = "PRE_46"
    content_seen = False

    def flush() -> None:
        nonlocal builder, seen_choice_in_question
        if builder is not None and builder.correct_letter is not None:
            out.append(builder.to_raw())
        builder = None
        seen_choice_in_question = False

    for raw_line in text.splitlines():
        if "\f" in raw_line:
            current_page += raw_line.count("\f")
            raw_line = raw_line.replace("\f", "")

        if not raw_line.strip():
            continue

        if ANCHORS["section_4_6_header"].match(raw_line):
            section_state = "IN_46"
            content_seen = False
            continue

        if ANCHORS["section_4_7_header"].match(raw_line):
            if section_state == "IN_46" and content_seen:
                flush()
                break
            section_state = "PRE_46"
            continue

        if section_state != "IN_46":
            continue

        if ANCHORS["footer"].match(raw_line):
            continue

        if ANCHORS["page_artifact"].match(raw_line):
            continue

        if ANCHORS["difficulty"].match(raw_line):
            continue

        if ANCHORS["passage_divider"].match(raw_line):
            continue

        m = ANCHORS["correct_answer_line"].match(raw_line)
        if m and builder is not None:
            builder.correct_letter = m.group(1)
            out.append(builder.to_raw())
            builder = None
            seen_choice_in_question = False
            continue

        m = ANCHORS["question_stem"].match(raw_line)
        if m:
            flush()
            builder = _Builder(global_number=int(m.group(1)), page=current_page)
            builder.stem_lines.append(m.group(2).strip())
            builder.state = "STEM"
            content_seen = True
            continue

        if builder is None:
            continue

        m = ANCHORS["choice"].match(raw_line)
        if m:
            letter = m.group(1)
            rest = m.group(2).strip()
            if builder.state in ("STEM", "STEM_ITEMS", "CHOICES"):
                builder.finalize_stem_item()
                builder.choices[letter] = [rest]
                builder.current_choice = letter
                builder.state = "CHOICES"
                seen_choice_in_question = True
            elif builder.state in ("CATEGORY", "OVERALL", "PER_CHOICE"):
                builder.per_choice[letter] = [rest]
                builder.current_per_choice = letter
                builder.state = "PER_CHOICE"
            continue

        if builder.state == "STEM" and not seen_choice_in_question:
            m = ANCHORS["stem_item"].match(raw_line)
            if m:
                builder.finalize_stem_item()
                builder.current_stem_item = {
                    "label": m.group(1),
                    "text": [m.group(2).strip()],
                }
                builder.state = "STEM_ITEMS"
                continue

        text_line = raw_line.strip()

        if builder.state == "CHOICES":
            if text_line in KNOWN_CATEGORIES:
                builder.category_lines.append(text_line)
                builder.state = "CATEGORY"
                continue
            if builder.current_choice is not None:
                builder.choices[builder.current_choice].append(text_line)
            continue

        if builder.state == "STEM":
            builder.stem_lines.append(text_line)
            continue

        if builder.state == "STEM_ITEMS":
            if builder.current_stem_item is not None:
                builder.current_stem_item["text"].append(text_line)
            continue

        if builder.state == "CATEGORY":
            builder.overall_lines.append(text_line)
            builder.state = "OVERALL"
            continue

        if builder.state == "OVERALL":
            builder.overall_lines.append(text_line)
            continue

        if builder.state == "PER_CHOICE" and builder.current_per_choice is not None:
            builder.per_choice[builder.current_per_choice].append(text_line)
            continue

    flush()
    return out
