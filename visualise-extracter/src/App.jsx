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
    name: "id",
    desc: "Stable hash-based ID for the question. Computed from the passage hash + position, so the same question across re-extractions keeps the same id.",
  },
  {
    name: "passage_id",
    desc: "ID of the reading-comprehension passage this question belongs to. Multiple questions can share one passage.",
  },
  {
    name: "position_in_passage",
    desc: "1-based index of this question within its passage (most passages have 3–4 questions).",
  },
  {
    name: "book_question_number",
    desc: "The number printed in the PDF (1, 2, 3 … 140). Use this to Cmd+F the question in the source PDF.",
  },
  {
    name: "question_text",
    desc: "The display-ready question. Any 'line N' / 'lines N–M' references in the original have been rewritten to 'paragraph N' / 'paragraphs N–M' using the passage's line→paragraph map. Safer for downstream rendering since paragraphs survive reflow but raw line numbers don't.",
  },
  {
    name: "question_text_verbatim",
    desc: "The exact stem text as printed in the PDF, before line-reference rewriting. Kept around so we can audit the rewrite and prove the extractor didn't fabricate text.",
  },
  {
    name: "roman_options",
    desc: "Roman-numeral sub-options (I., II., III. …) that appear inside the stem on some 'which of the following' questions. null when the stem has no sub-list. Only ~1 % of questions use this format.",
  },
  {
    name: "choices",
    desc: "The five answer choices A–E, with whitespace normalized.",
  },
  {
    name: "correct_answer",
    desc: "The correct letter (A–E), pulled from §4.5 Answer Key and cross-checked against §4.6 Answer Explanations.",
  },
  {
    name: "explanation.summary",
    desc: "The lead paragraph from §4.6 — discusses the question as a whole before going choice-by-choice.",
  },
  {
    name: "explanation.A … E",
    desc: "Per-choice explanation paragraph. The correct one is prefixed with the literal word 'Correct.' in the source PDF, so it's easy to spot.",
  },
  {
    name: "tags",
    desc: "Source-tag (e.g. ogvr-24-25), 'reading_comprehension', difficulty (easy/medium/hard), and the RC category (supporting_idea, inference, evaluation, application, main_idea, logical_structure, …).",
  },
  {
    name: "source",
    desc: "Provenance: which book and which PDF page the question came from.",
  },
];

const PASSAGE_GLOSSARY = [
  {
    name: "id",
    desc: "Hash-based ID derived from the passage's full text. Two reprints of the same passage in different books share this id.",
  },
  {
    name: "paragraphs",
    desc: "The passage broken into paragraphs. Used by the rewriter to translate 'line N' references into 'paragraph N' references.",
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

function pickTags(tags) {
  const difficulty = tags.find((t) => ["easy", "medium", "hard"].includes(t));
  const category = tags.find(
    (t) =>
      ![
        "easy",
        "medium",
        "hard",
        "reading_comprehension",
        "ogvr-24-25",
        "ogvr-25-26",
      ].includes(t)
  );
  return { difficulty, category };
}

function JsonView({ value }) {
  const text = useMemo(() => JSON.stringify(value, null, 2), [value]);
  return <pre className="json-block">{text}</pre>;
}

function Sidebar({ samples, activeIdx, onSelect, onShowGlossary }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-title">10 sampled questions</div>
      <ol className="sidebar-list">
        {samples.map((s, i) => {
          const { difficulty, category } = pickTags(s.question.tags);
          return (
            <li
              key={i}
              className={`sidebar-item ${i === activeIdx ? "active" : ""}`}
              onClick={() => onSelect(i)}
            >
              <div className="sidebar-row">
                <span className="badge book">{s.book_tag}</span>
                <span
                  className="badge diff"
                  style={{ background: DIFFICULTY_COLOR[difficulty] }}
                >
                  {difficulty}
                </span>
              </div>
              <div className="sidebar-row sidebar-meta">
                <span className="qnum">Q{s.global_number}</span>
                <span className="cat">{category}</span>
              </div>
              <div className="sidebar-row sidebar-flags">
                {s.stem_was_rewritten && (
                  <span
                    className="flag rewrite"
                    title="question_text differs from question_text_verbatim — 'line N' references rewritten to 'paragraph N' using the passage's line→paragraph map"
                  >
                    line→passage
                  </span>
                )}
                {s.has_roman_options && (
                  <span
                    className="flag roman"
                    title="stem contains Roman-numeral sub-options I/II/III"
                  >
                    I·II·III
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
  const { difficulty, category } = pickTags(sample.question.tags);
  return (
    <section className="left-panel">
      <h2 className="panel-title">Source PDF — manual verify</h2>
      <div className="kv">
        <div className="k">PDF file</div>
        <div className="v">
          <code>{sample.book_pdf}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">Book tag</div>
        <div className="v">
          <code>{sample.book_tag}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">Question number in book</div>
        <div className="v">
          <span className="big-q">Q{sample.global_number}</span>
        </div>
      </div>
      <div className="kv">
        <div className="k">Difficulty</div>
        <div className="v">
          <span
            className="badge diff"
            style={{ background: DIFFICULTY_COLOR[difficulty] }}
          >
            {difficulty}
          </span>
        </div>
      </div>
      <div className="kv">
        <div className="k">Category (RC question type)</div>
        <div className="v">
          <code>{category}</code>
        </div>
      </div>
      <div className="kv">
        <div className="k">How to verify manually</div>
        <div className="v">
          <ol className="howto">
            <li>
              Open <code>{sample.book_pdf}</code> in any PDF viewer.
            </li>
            <li>
              Use <kbd>Cmd</kbd>+<kbd>F</kbd> and search for{" "}
              <code>{sample.search_hint}</code> in §4.4 (Practice Questions).
            </li>
            <li>
              Compare the printed question + 5 choices against the JSON on the
              right.
            </li>
            <li>
              For the explanation, search the same number in §4.6 (Answer
              Explanations).
            </li>
          </ol>
        </div>
      </div>
      <details className="passage-details">
        <summary>Linked passage (rendered)</summary>
        <div className="passage-body">
          {sample.passage.paragraphs.map((p, i) => (
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
  const [tab, setTab] = useState("question");
  return (
    <section className="right-panel">
      <div className="tab-row">
        <button
          className={`tab ${tab === "question" ? "active" : ""}`}
          onClick={() => setTab("question")}
        >
          question.json
        </button>
        <button
          className={`tab ${tab === "passage" ? "active" : ""}`}
          onClick={() => setTab("passage")}
        >
          passage.json
        </button>
      </div>
      {tab === "question" ? (
        <JsonView value={sample.question} />
      ) : (
        <JsonView value={sample.passage} />
      )}
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
          <h3>question.json fields</h3>
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
          <h3>passage.json fields</h3>
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
            Manual spot-check dashboard — 10 diverse questions extracted from
            two GMAT Verbal Review books. Each entry shows the source PDF +
            question number on the left, and the structured JSON on the right.
            Click <em>“What do these field names mean?”</em> in the sidebar
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
