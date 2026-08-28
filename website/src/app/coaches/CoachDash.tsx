"use client";
import { useState } from "react";
import { Reveal } from "@/components/ui/Reveal";
import { coaches } from "@/content/site";
import { track } from "@/lib/analytics";

/**
 * The coach dashboard, and the panel that teaches a coach how to read it.
 *
 * Two states behind tabs. The point is that the same screen is worth opening
 * twice in a week — on Tuesday it says "on track", on Friday it says "half the
 * squad has not prepped for tomorrow". A single static state cannot show that,
 * and an animation would be a demo rather than a proof. Keep it to two.
 *
 * Tabs are real buttons in a tablist, so this works from the keyboard.
 */
const { dash } = coaches;

export function CoachDash() {
  const [active, setActive] = useState(0);
  const st = dash.states[active];

  return (
    <section id="coach-dashboard" className="section surface-dark" aria-labelledby="cd-h">
      <div className="container">
        <div className="section-head">
          <span className="coach-badge">{dash.badge}</span>
          <h2 id="cd-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{dash.h2}</h2>
          <p className="body muted-txt">{dash.sub}</p>
        </div>

        <Reveal className="dashwrap">
          <div className="dash">
            <div className="dash__top">
              <b>{dash.team}</b>
              <div className="dash__tabs" role="tablist" aria-label="Example days">
                {dash.states.map((s, i) => (
                  <button
                    key={s.id}
                    role="tab"
                    type="button"
                    id={`dtab-${s.id}`}
                    aria-selected={i === active}
                    aria-controls={`dpanel-${s.id}`}
                    className={i === active ? "is-on" : undefined}
                    onClick={() => { setActive(i); track("coach_dash_state", { state: s.id }); }}
                  >
                    {s.tab}
                  </button>
                ))}
              </div>
            </div>

            <div id={`dpanel-${st.id}`} role="tabpanel" aria-labelledby={`dtab-${st.id}`}>
              <p className="dash__week-label">{st.week}</p>

              <ul className="dash__metrics">
                {st.metrics.map((m) => (
                  <li key={m.label}>
                    <span className="dash__label">{m.label}</span>
                    {/* A percentage gets the big numeral; a phrase like "Most of
                        the squad" gets a smaller size so it does not wrap to
                        three lines in a half-width tile. */}
                    <b className={`dash__value${/%$/.test(m.value) ? "" : " dash__value--phrase"}`}>{m.value}</b>
                    <span className="dash__bar" aria-hidden><i style={{ width: `${m.pct}%` }} /></span>
                    <span className="dash__note">{m.note}</span>
                  </li>
                ))}
              </ul>

              {/* Scrolls horizontally under 620px rather than crushing seven
                  columns into 350px. data-today marks the column the mobile
                  layout snaps to, so a coach opening this on a phone lands on
                  the day the panel is talking about. */}
              <div className="dash__week-scroll">
                <ol className="dash__week" aria-label="The week as scheduled">
                  {dash.days.map((d) => (
                    <li
                      key={d.d}
                      data-today={d.d === st.today ? "" : undefined}
                      className={"game" in d && d.game ? "is-game" : "train" in d && d.train ? "is-train" : undefined}
                    >
                      <b>{d.d}</b>{d.k}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </div>

          {/* Teaches the coach to read the screen. Names a pattern, never a
              diagnosis, and hands individual guidance back to the app. */}
          <aside className="dash__read" aria-live="polite">
            <span className="eyebrow">{dash.readTitle}</span>
            <h3 className="dash__read-h">{st.read.h}</h3>
            <p className="dash__read-p">{st.read.p}</p>

            {/* Drawn, not wired — see dash.action in site.ts. A <span>, not a
                <button>: this is part of the illustration, and a control that
                looks live and does nothing when a coach presses it is worse
                than a picture of one. Swap it for a real button the day the
                product can send the reminder. */}
            <span className="dash__action" aria-hidden>
              <span className="dash__action-arrow">→</span>{dash.action}
            </span>

            <p className="dash__read-foot">{dash.readFoot}</p>
          </aside>
        </Reveal>
      </div>
    </section>
  );
}
