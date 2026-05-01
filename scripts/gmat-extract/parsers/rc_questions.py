"""State-machine parser for §4.4 (Practice Questions: Reading Comprehension).

Consumes pdftotext -layout output for the RC questions page range; emits
RawPassage and RawQuestion records. The joiner downstream attaches answers
and explanations.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .common import ANCHORS, normalize_for_match


@dataclass
class RawPassage:
    paragraphs: list[str]
    intro_note: str | None
    line_to_paragraph: dict[int, int]
    page: int
    passage_index_in_book: int
    difficulty: str


@dataclass
class RawQuestion:
    global_number: int
    passage_index: int
    stem_original: str
    stem_items: list[dict[str, str]] | None
    choices: dict[str, str]
    difficulty: str
    page: int


@dataclass
class _PassageBuilder:
    intro_note: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    line_to_paragraph: dict[int, int] = field(default_factory=dict)
    body_indent: int | None = None
    first_indent: int | None = None
    current_paragraph: list[str] = field(default_factory=list)
    page: int = 0

    def push_line(self, raw: str, leading_spaces: int, line_marker: int | None) -> None:
        text = raw.strip()
        if not text:
            return
        # First line of the passage: stash its indent as the paragraph indent of
        # the first paragraph, but don't lock body_indent yet — we need a body
        # (continuation) line to know the *body* indent (typically 3 less than
        # the paragraph indent for OG passages).
        if self.first_indent is None:
            self.first_indent = leading_spaces
            self.current_paragraph.append(text)
            self.line_to_paragraph.setdefault(1, 1)
            if line_marker is not None:
                self.line_to_paragraph[line_marker] = 1
            return
        # Second line: lock body_indent. If it's less indented than the first
        # line, this is a body-of-paragraph continuation and its column is the
        # body indent. Otherwise the first line was already body-aligned.
        if self.body_indent is None:
            self.body_indent = (
                leading_spaces if leading_spaces < self.first_indent
                else self.first_indent
            )
        is_break = (
            leading_spaces - self.body_indent >= 3
            and (text[:1].isupper() or text[:1] in "“\"‘'")
        )
        if is_break and self.current_paragraph:
            self.paragraphs.append(" ".join(self.current_paragraph))
            self.current_paragraph = [text]
        else:
            self.current_paragraph.append(text)
        # Set line_to_paragraph AFTER we've decided whether this line broke a
        # paragraph — so a marker line that coincides with a new paragraph maps
        # to the new paragraph, not the old one.
        if line_marker is not None:
            self.line_to_paragraph[line_marker] = len(self.paragraphs) + 1

    def finalize(self) -> tuple[list[str], dict[int, int]]:
        if self.current_paragraph:
            self.paragraphs.append(" ".join(self.current_paragraph))
            self.current_paragraph = []
        return self.paragraphs, _densify_line_map(self.line_to_paragraph)


def _densify_line_map(sparse: dict[int, int]) -> dict[int, int]:
    """Markers appear every 5 lines; densify so any line N has a paragraph entry."""
    if not sparse:
        return {}
    max_line = max(sparse) + 4
    sorted_markers = sorted(sparse.items())
    dense: dict[int, int] = {}
    last_para = sorted_markers[0][1]
    marker_idx = 0
    for n in range(1, max_line + 1):
        while (
            marker_idx < len(sorted_markers)
            and sorted_markers[marker_idx][0] <= n
        ):
            last_para = sorted_markers[marker_idx][1]
            marker_idx += 1
        dense[n] = last_para
    return dense


@dataclass
class _QuestionBuilder:
    global_number: int
    passage_index: int
    stem_lines: list[str] = field(default_factory=list)
    stem_items: list[dict[str, str]] = field(default_factory=list)
    current_stem_item: dict[str, list[str]] | None = None
    choices: dict[str, list[str]] = field(default_factory=dict)
    current_choice: str | None = None
    difficulty: str = ""
    page: int = 0

    def attach_continuation(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.current_choice is not None:
            self.choices[self.current_choice].append(text)
        elif self.current_stem_item is not None:
            self.current_stem_item["text"].append(text)
        else:
            self.stem_lines.append(text)

    def finalize_current_stem_item(self) -> None:
        if self.current_stem_item is not None:
            self.stem_items.append(
                {
                    "label": self.current_stem_item["label"],
                    "text": " ".join(self.current_stem_item["text"]),
                }
            )
            self.current_stem_item = None

    def to_raw(self) -> RawQuestion:
        self.finalize_current_stem_item()
        return RawQuestion(
            global_number=self.global_number,
            passage_index=self.passage_index,
            stem_original=normalize_for_match(" ".join(self.stem_lines)),
            stem_items=self.stem_items or None,
            choices={k: normalize_for_match(" ".join(v)) for k, v in self.choices.items()},
            difficulty=self.difficulty,
            page=self.page,
        )


def parse(text: str, page_offset: int = 1) -> tuple[list[RawPassage], list[RawQuestion]]:
    """Parse §4.4 text. `page_offset` is the PDF page number of line 1 of `text`.

    Page tracking is approximate (we count form-feeds emitted by `pdftotext -layout`
    when invoked with `-eol unix`; without that flag pages are concatenated and we
    fall back to the explicit page-range start).
    """
    passages: list[RawPassage] = []
    questions: list[RawQuestion] = []

    current_difficulty = ""
    passage_builder: _PassageBuilder | None = None
    question_builder: _QuestionBuilder | None = None
    state = "IDLE"
    seen_choice_in_question = False
    current_page = page_offset
    section_state = "PRE_44"
    content_seen = False

    def flush_question() -> None:
        nonlocal question_builder, seen_choice_in_question
        if question_builder is not None:
            questions.append(question_builder.to_raw())
        question_builder = None
        seen_choice_in_question = False

    def flush_passage() -> None:
        nonlocal passage_builder
        if passage_builder is None:
            return
        paragraphs, line_to_para = passage_builder.finalize()
        passages.append(
            RawPassage(
                paragraphs=paragraphs,
                intro_note=passage_builder.intro_note,
                line_to_paragraph=line_to_para,
                page=passage_builder.page,
                passage_index_in_book=len(passages) + 1,
                difficulty=current_difficulty,
            )
        )
        passage_builder = None

    for raw_line in text.splitlines():
        if "\f" in raw_line:
            current_page += raw_line.count("\f")
            raw_line = raw_line.replace("\f", "")

        if not raw_line.strip():
            continue

        if ANCHORS["section_4_4_header"].match(raw_line):
            section_state = "IN_44"
            content_seen = False
            continue

        if ANCHORS["section_4_5_header"].match(raw_line):
            if section_state == "IN_44" and content_seen:
                break
            section_state = "PRE_44"
            continue

        if section_state != "IN_44":
            continue

        if ANCHORS["footer"].match(raw_line):
            continue

        if ANCHORS["page_artifact"].match(raw_line):
            continue

        m = ANCHORS["difficulty"].match(raw_line)
        if m:
            flush_question()
            flush_passage()
            current_difficulty = m.group(3).lower()
            state = "IDLE"
            content_seen = True
            continue

        m = ANCHORS["passage_start"].match(raw_line)
        if m:
            flush_question()
            flush_passage()
            passage_builder = _PassageBuilder(page=current_page)
            content_seen = True
            tail = raw_line[m.end():]
            stripped_tail = tail.strip()
            if stripped_tail:
                # Content column = end of "Line" + leading whitespace of tail.
                # Using raw_line's leading spaces would point at column 0 of
                # "Line", which is *less* indented than body lines — breaking
                # the indent-shift heuristic.
                content_col = m.end() + (len(tail) - len(tail.lstrip(" ")))
                passage_builder.push_line(stripped_tail, content_col, None)
            state = "IN_PASSAGE"
            continue

        m = ANCHORS["passage_divider"].match(raw_line)
        if m:
            state = "POST_PASSAGE_MARKER"
            continue

        if state == "IN_PASSAGE":
            m = ANCHORS["line_marker"].match(raw_line)
            if m:
                line_no = int(m.group(1))
                stripped = raw_line[m.end():]
                # The line_marker regex ends with `\s*`, so m.end() is exactly
                # the column of the first non-space char of the content. That
                # is what should be compared against body_indent — not the raw
                # whitespace before the marker (which sits at col 6 regardless
                # of where the content starts).
                content_col = m.end()
                passage_builder.push_line(stripped, content_col, line_no)
            else:
                leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
                passage_builder.push_line(raw_line, leading_spaces, None)
            continue

        m = ANCHORS["question_stem"].match(raw_line)
        if m and current_difficulty:
            flush_question()
            pending_passage_index = len(passages) if passage_builder is not None else len(passages) - 1
            question_builder = _QuestionBuilder(
                global_number=int(m.group(1)),
                passage_index=pending_passage_index,
                difficulty=current_difficulty,
                page=current_page,
            )
            question_builder.stem_lines.append(m.group(2).strip())
            state = "IN_QUESTION_STEM"
            continue

        if question_builder is not None:
            m = ANCHORS["choice"].match(raw_line)
            if m:
                question_builder.finalize_current_stem_item()
                letter = m.group(1)
                question_builder.choices[letter] = [m.group(2).strip()]
                question_builder.current_choice = letter
                seen_choice_in_question = True
                state = "IN_CHOICES"
                continue

            if not seen_choice_in_question:
                m = ANCHORS["stem_item"].match(raw_line)
                if m:
                    question_builder.finalize_current_stem_item()
                    question_builder.current_stem_item = {
                        "label": m.group(1),
                        "text": [m.group(2).strip()],
                    }
                    state = "IN_STEM_ITEMS"
                    continue

            question_builder.attach_continuation(raw_line)

    flush_question()
    flush_passage()

    return passages, questions
