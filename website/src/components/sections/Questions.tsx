"use client";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { questions } from "@/content/site";
import { track } from "@/lib/analytics";

/**
 * S3 — "Pick a question, see the day" (section spec, treatment 1b).
 * Recognition, then proof: the parent picks their own question and the app
 * answers it as a real fueling timeline. Demos the product, doesn't describe it.
 *
 * Selection is client-side only — no URL change, no scroll jump. The panel has a
 * fixed min-height so switching questions cannot shift layout (CLS stays 0).
 */
export function Questions() {
  const [i, setI] = useState(0);
  const base = useId();
  const btns = useRef<(HTMLButtonElement | null)[]>([]);
  /* Three on the homepage, not four. The fourth ("between two games") overlaps
     the tournament question — same weekend, narrower slice — and a fourth
     near-identical option costs recognition rather than adding it. It still
     exists in the array because it has its own /questions/[slug] page linked
     from /faq. See questions.homeCount in site.ts. */
  const items = questions.items.slice(0, questions.homeCount);
  const active = items[i];

  function select(next: number) {
    if (next === i) return;
    setI(next);
    /* On mobile the questions are a horizontal scroller. Without this, tapping
       the sliver of the next card selects it and leaves it half off-screen —
       the answer below changes for a question you cannot fully read. Harmless
       on desktop, where the list is a static column and nothing scrolls. */
    btns.current[next]?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
    track("question_select", { index: next, label: items[next].q });
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    const step = keys[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const next = (i + step + items.length) % items.length;
    select(next);
    btns.current[next]?.focus();
  }

  return (
    <section id="questions" className="section surface-light qs" aria-labelledby="qs-h">
      <div className="container">
        <header className="qs__head">
          <span className="eyebrow qs__eyebrow">{questions.eyebrow}</span>
          <h2 id="qs-h" className="qs__h2">{questions.h2}</h2>
        </header>

        <div className="qs__grid">
          <div className="qs__list">
            <div role="tablist" aria-label="Questions parents ask" className="qs__tabs" onKeyDown={onKey}>
              {items.map((it, n) => (
                <button
                  key={it.slug}
                  ref={(el) => { btns.current[n] = el; }}
                  role="tab"
                  id={`${base}-t${n}`}
                  aria-selected={n === i}
                  aria-controls={`${base}-p`}
                  tabIndex={n === i ? 0 : -1}
                  className={`qs__q${n === i ? " is-on" : ""}`}
                  onClick={() => select(n)}
                >
                  <span>{it.q}</span>
                  <span className="qs__arrow" aria-hidden>→</span>
                </button>
              ))}
            </div>
            <p className="qs__note">{questions.listNote}</p>
          </div>

          <div
            id={`${base}-p`}
            role="tabpanel"
            aria-live="polite"
            aria-labelledby={`${base}-t${i}`}
            className="qs__panel surface-dark"
          >
            <div className="qs__fade" key={active.slug}>
              <span className="qs__badge">{active.badge}</span>
              <h3 className="qs__q3">{active.q}</h3>
              <p className="qs__answer">{active.answer}</p>
              <ol className="qs__rows">
                {active.rows.map((r, n) => (
                  <li
                    key={r.label}
                    className={`qs__row${r.event ? " qs__row--event" : ""}`}
                    style={{ ["--d" as string]: `${n * 45}ms` }}
                  >
                    <span className="qs__time">{r.time}</span>
                    <span className={`qs__dot${r.event ? " qs__dot--event" : ""}`} aria-hidden />
                    <span className="qs__label">{r.label}</span>
                    {r.note && <span className="qs__rownote">{r.note}</span>}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
