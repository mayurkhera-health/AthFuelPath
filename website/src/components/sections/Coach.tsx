"use client";
import { useEffect, useRef } from "react";
import { Shot } from "@/components/ui/Shot";
import { coach } from "@/content/site";
import { track } from "@/lib/analytics";

/**
 * AI Fuel Coach (S5b). Sits between "What to cook" and the dietitian section so
 * the page reads as one escalating argument: the plan handles the week → a
 * question comes up anyway → ask the Coach → when it needs a human, book one.
 *
 * The device is a real capture and is marked alt="" on purpose: the same
 * exchange is transcribed word for word in the <figcaption> underneath, so the
 * text is what a screen reader announces and what a search engine indexes.
 * Never let the two drift apart.
 *
 * No CTA here by design: the sections directly above and below both carry one,
 * and a third inside one screen reads as pressure rather than help.
 *
 * No bridge line either. It used to end on "when a question needs a human, we
 * don't pretend software should answer it" — immediately above a section headed
 * "A real dietitian, when the app isn't enough". Same sentiment twice, with a
 * surface flip in between, which is what made the seam obvious. The next
 * section's headline is the bridge.
 */
export function Coach() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(
      (es) =>
        es.forEach((e) => {
          if (!e.isIntersecting) return;
          track("ai_coach_section_view");
          coach.situations.forEach((s) =>
            track("ai_coach_example_view", { scenario: s.label.toLowerCase().replace(/\s+/g, "_") }),
          );
          io.disconnect();
        }),
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const t = coach.transcript;

  return (
    <section id="ai-coach" ref={ref} className="section surface-light coach" aria-labelledby="co-h">
      <div className="container coach__grid">
        <div className="coach__copy">
          <div className="coach__head">
            <span className="eyebrow">{coach.eyebrow}</span>
            <h2 id="co-h" className="h2 balance coach__h2">{coach.h2}</h2>
            <p className="body muted-txt">{coach.body}</p>
          </div>

          <ul className="coach__sits">
            {coach.situations.map((s) => (
              <li key={s.label}>
                <span className="eyebrow coach__sit-label">{s.label}</span>
                <p className="coach__sit-q">&ldquo;{s.q}&rdquo;</p>
              </li>
            ))}
          </ul>

        </div>

        <figure className="coach__proof">
          <Shot
            src="/screens/coach-chat.webp"
            w={735}
            h={1390}
            alt=""
            className="coach__shot"
          />
          {/* Word-for-word transcript of the capture above.
              The caption line is visible; the transcript itself is sr-only —
              printing it again under the picture would be the same content twice
              and would blow the 900px ceiling. Hidden here means hidden from
              sighted users only: it is real DOM text, so screen readers announce
              it and search engines index it, which is the whole point. */}
          <figcaption className="coach__script">
            <p className="coach__script-cap">{t.caption}</p>
            <div className="sr-only">
              <p>Question: {t.question}</p>
              <p>Fuel Coach: {t.intro}</p>
              <p>{t.listHead}</p>
              <ul>
                {t.list.map((l) => (
                  <li key={l.food}>{l.food} ({l.why})</li>
                ))}
              </ul>
              <p>{t.avoid}</p>
              <p>{t.followUp}</p>
            </div>
            <p className="coach__src">{t.source}</p>
          </figcaption>
        </figure>
      </div>

      <div className="container">
        <div className="coach__row">
          <div className="coach__travel">
            <p className="coach__travel-h">{coach.travel.h}</p>
            <p className="coach__travel-p">{coach.travel.p}</p>
            <p className="coach__travel-priv">{coach.travel.privacy}</p>
          </div>
          <div>
            <p className="coach__safety"><strong>{coach.safety.h}</strong> {coach.safety.p}</p>
            <p className="coach__personas">{coach.personas}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
