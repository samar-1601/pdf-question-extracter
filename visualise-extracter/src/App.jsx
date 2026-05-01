import { useEffect, useMemo, useState } from "react";
import samples from "./data/samples.json";

const THEME_KEY = "viz-theme";

function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    return window.localStorage.getItem(THEME_KEY) || "dark";
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);
  return [theme, setTheme];
}

const DIFFICULTY_COLOR = {
  easy: "#16a34a",
  medium: "#d97706",
  hard: "#dc2626",
};

const FIELD_GLOSSARY = [
  {
    name: "number",
    desc: "The number printed in the PDF (1, 2, 3 … 140). Use this to Cmd+F the question in the source PDF.",
  },
  {
    name: "question_text",
    desc: "Display-ready stem. (1) line-N references rewritten to paragraph-N references using the passage's line→paragraph map. (2) If the question has roman_options, the I./II./III. items are appended at the end so the stem is self-contained for the DB (which only stores A–E).",
  },
  {
    name: "options",
    desc: "The five answer choices A–E, with whitespace normalized.",
  },
  {
    name: "question_type",
    desc: "RC question category from §4.6 — Supporting Idea / Inference / Main Idea / Application / Logical Structure / Style and Tone / Evaluation.",
  },
  {
    name: "rationale",
    desc: "The lead paragraph from §4.6 — discusses the question as a whole before going choice-by-choice.",
  },
  {
    name: "option_explanations",
    desc: "Per-choice explanation paragraph. The correct one is prefixed with the literal word 'Correct.' in the source PDF, so it's easy to spot.",
  },
  {
    name: "correct_answer",
    desc: "The correct letter (A–E), pulled from §4.5 Answer Key and cross-checked against §4.6 Answer Explanations.",
  },
  {
    name: "position_in_passage",
    desc: "1-based contiguous index of this question within its passage (Q1, Q2, Q3 …). Distinct from `number`.",
  },
  {
    name: "difficulty",
    desc: "easy / medium / hard. Top-level on each question; also duplicated inside `tags`.",
  },
  {
    name: "question_text_verbatim",
    desc: "The exact stem text as printed in the PDF, before line-ref rewriting and before roman-options embedding. Kept around so we can audit the rewrite and prove the extractor didn't fabricate text.",
  },
  {
    name: "roman_options",
    desc: "Roman-numeral sub-options (I., II., III. …) that appear inside the stem on some 'which of the following' questions. Now also embedded inside `question_text` so downstream code that only reads `question_text` doesn't lose them. null when the stem has no sub-list. Only ~1 % of questions use this format.",
  },
  {
    name: "id",
    desc: "Stable hash-based question ID. Computed from passage hash + position, so the same question across re-extractions keeps the same id.",
  },
  {
    name: "tags",
    desc: "Source-tag (e.g. ogvr-24-25), 'reading_comprehension', difficulty, and the slugified RC category.",
  },
  {
    name: "source",
    desc: "Provenance: which book and which PDF page the question came from.",
  },
];

const PASSAGE_GLOSSARY = [
  {
    name: "passage_id",
    desc: "Sequential 1-based passage number within the book (1, 2, 3 …). Use this to Cmd+F the passage's first line in the source PDF.",
  },
  {
    name: "passage_paragraphs",
    desc: "The passage broken into paragraphs, in printed-book order. Used by the rewriter to translate 'line N' references into 'paragraph N' references — and by downstream notes that discuss the function of each paragraph.",
  },
  {
    name: "questions",
    desc: "All questions linked to this passage, ordered by their book number.",
  },
  {
    name: "id",
    desc: "Stable hash-based passage ID derived from the passage's full text. Two reprints of the same passage in different books share this id.",
  },
  {
    name: "difficulty",
    desc: "Top-level field, mirrors the band of the questions that reference this passage. Duplicated inside `tags`.",
  },
  {
    name: "intro_note",
    desc: "Optional editor's note that sometimes precedes the passage (e.g. 'The following is excerpted from a 1990 article …'). null when absent.",
  },
  {
    name: "line_to_paragraph",
    desc: "Map from each line number printed in the PDF to the paragraph (1-based) that line lives in. Densified — every line number has an entry, not just the (5)-marked ones.",
  },
  {
    name: "tags",
    desc: "Source-tag and difficulty band (matching the band of the questions that reference it).",
  },
  {
    name: "sources",
    desc: "Books that contain this passage. An array because the same passage can be reprinted across editions.",
  },
];

function JsonView({ value }) {
  const text = useMemo(() => JSON.stringify(value, null, 2), [value]);
  return <pre className="json-block">{text}</pre>;
}

function Sidebar({ samples, activeIdx, onSelect, onShowGlossary }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-title">{samples.length} passage blocks</div>
      <ol className="sidebar-list">
        {samples.map((s, i) => {
          const diffs = s.flags?.difficulties || [];
          const npara = s.passage_paragraphs.length;
          return (
            <li
              key={i}
              className={`sidebar-item ${i === activeIdx ? "active" : ""}`}
              onClick={() => onSelect(i)}
            >
              <div className="sidebar-row">
                <span className="badge book">{s.book_tag}</span>
                {diffs.map((d) => (
                  <span
                    key={d}
                    className="badge diff"
                    style={{ background: DIFFICULTY_COLOR[d] || "#475569" }}
                  >
                    {d}
                  </span>
                ))}
              </div>
              <div className="sidebar-row sidebar-meta">
                <span className="qnum">
                  Passage #{s.passage_id} ·{" "}
                  Q{s.first_question_number}+ ({s.questions.length})
                </span>
                <span className="cat">
                  {npara} paragraph{npara === 1 ? "" : "s"}
                </span>
              </div>
              <div className="sidebar-row sidebar-flags">
                {s.flags?.has_line_ref_rewrite && (
                  <span
                    className="flag rewrite"
                    title="at least one question's question_text differs from question_text_verbatim — line→paragraph rewrite fired"
                  >
                    line→passage
                  </span>
                )}
                {s.flags?.has_roman_options && (
                  <span
                    className="flag roman"
                    title="passage has at least one question with roman_options sub-list (I/II/III)"
                  >
                    I·II·III
                  </span>
                )}
                {s.flags?.needs_paragraph_review && (
                  <span
                    className="flag review"
                    title="1-paragraph passage — needs visual verification against the printed PDF"
                  >
                    review
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <button className="glossary-btn" onClick={onShowGlossary}>
        ? What do these field names mean?
      </button>
    </nav>
  );
}

function LeftPanel({ sample }) {
  const { passage_paragraphs, book_pdf, book_tag, questions, flags, passage_id } = sample;
  const firstQ = questions[0]?.number;
  const lastQ = questions[questions.length - 1]?.number;
  return (
    <section className="left-panel">
      <h2 className="panel-title">Source PDF — manual verify</h2>
      <div className="kv">
        <div className="k">PDF file</div>
        <div className="v">
          <code>{book_pdf}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">Book tag</div>
        <div className="v">
          <code>{book_tag}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">Passage number in book</div>
        <div className="v">
          <code>passage_id: {passage_id}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">Question numbers in book</div>
        <div className="v">
          <span className="big-q">
            Q{firstQ}–Q{lastQ}
          </span>
          <span style={{ marginLeft: 8, color: "var(--muted)" }}>
            ({questions.length} total)
          </span>
        </div>
      </div>
      <div className="kv">
        <div className="k">Difficulty mix</div>
        <div className="v">
          {(flags?.difficulties || []).map((d) => (
            <span
              key={d}
              className="badge diff"
              style={{
                background: DIFFICULTY_COLOR[d] || "#475569",
                marginRight: 4,
              }}
            >
              {d}
            </span>
          ))}
        </div>
      </div>
      <div className="kv">
        <div className="k">Paragraph count</div>
        <div className="v">
          <code>{passage_paragraphs.length}</code>
          {flags?.needs_paragraph_review && (
            <span
              style={{
                marginLeft: 8,
                color: "var(--muted)",
                fontSize: 12,
              }}
            >
              (1-paragraph — please verify against the printed PDF)
            </span>
          )}
        </div>
      </div>
      <div className="kv">
        <div className="k">How to verify manually</div>
        <div className="v">
          <ol className="howto">
            <li>
              Open <code>{book_pdf}</code> in any PDF viewer.
            </li>
            <li>
              Use <kbd>Cmd</kbd>+<kbd>F</kbd> to find each question number
              (Q{firstQ}–Q{lastQ}) in §4.4 (Practice Questions).
            </li>
            <li>
              Compare each printed question + 5 choices against the JSON on
              the right.
            </li>
            <li>
              Compare the rendered passage below against the printed passage —
              especially the paragraph boundaries.
            </li>
            <li>
              For explanations, search the same number in §4.6 (Answer
              Explanations).
            </li>
          </ol>
        </div>
      </div>
      <details className="passage-details" open>
        <summary>Rendered passage ({passage_paragraphs.length} ¶)</summary>
        <div className="passage-body">
          {passage_paragraphs.map((p, i) => (
            <p key={i} className="passage-para">
              <span className="para-idx">¶{i + 1}</span> {p}
            </p>
          ))}
        </div>
      </details>
    </section>
  );
}

function RightPanel({ sample }) {
  return (
    <section className="right-panel">
      <details className="block-details" open>
        <summary>full passage block (combined JSON)</summary>
        <JsonView value={sample} />
      </details>
      <details className="block-details">
        <summary>passage fields only (no questions[])</summary>
        <JsonView
          value={Object.fromEntries(
            Object.entries(sample).filter(
              ([k]) =>
                k !== "questions" &&
                k !== "book_tag" &&
                k !== "book_pdf" &&
                k !== "first_question_number" &&
                k !== "flags"
            )
          )}
        />
      </details>
      {sample.questions.map((q) => (
        <details key={q.id} className="block-details">
          <summary>
            Q{q.number} — pos {q.position_in_passage} · {q.difficulty}
            {q.roman_options ? " · I·II·III" : ""}
          </summary>
          <JsonView value={q} />
        </details>
      ))}
    </section>
  );
}

function GlossaryModal({ onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Field glossary</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">
          <h3>passage block — top-level fields</h3>
          <dl className="glossary">
            {PASSAGE_GLOSSARY.map((entry) => (
              <div key={entry.name} className="glossary-entry">
                <dt>
                  <code>{entry.name}</code>
                </dt>
                <dd>{entry.desc}</dd>
              </div>
            ))}
          </dl>
          <h3>question fields (inside questions[])</h3>
          <dl className="glossary">
            {FIELD_GLOSSARY.map((entry) => (
              <div key={entry.name} className="glossary-entry">
                <dt>
                  <code>{entry.name}</code>
                </dt>
                <dd>{entry.desc}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [idx, setIdx] = useState(0);
  const [showGlossary, setShowGlossary] = useState(false);
  const [theme, setTheme] = useTheme();
  const sample = samples[idx];
  return (
    <div className="app">
      <header className="app-header">
        <div>
          <div className="app-title">GMAT RC Extraction Visualiser</div>
          <div className="app-sub">
            All {samples.length} passage blocks (
            {samples.reduce((n, s) => n + s.questions.length, 0)} questions)
            from two GMAT Verbal Review books. Each block combines the passage
            and every question that references it into a single JSON record.
            Click <em>"What do these field names mean?"</em> in the sidebar
            for a glossary.
          </div>
        </div>
        <button
          className="theme-toggle"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? "☀ Light" : "☾ Dark"}
        </button>
      </header>
      <div className="app-body">
        <Sidebar
          samples={samples}
          activeIdx={idx}
          onSelect={setIdx}
          onShowGlossary={() => setShowGlossary(true)}
        />
        <main className="main-pane">
          <LeftPanel sample={sample} />
          <RightPanel sample={sample} />
        </main>
      </div>
      {showGlossary && <GlossaryModal onClose={() => setShowGlossary(false)} />}
    </div>
  );
}
