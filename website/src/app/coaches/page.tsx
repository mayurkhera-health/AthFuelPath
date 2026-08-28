import { Reveal } from "@/components/ui/Reveal";
import { CoachForm } from "./CoachForm";
import { coaches } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "For coaches",
  description:
    "Fueling decides the second game of a tournament. AthFuelPath gives coaches and athletic directors a team-level view of how the squad is fueling, with nothing to set up and no individual athlete data.",
  path: "/coaches",
  image: "/og/coaches.jpg",
  imageAlt: "AthFuelPath for coaches — a team-level view of how the squad is fueling.",
});

/**
 * Coaches Corner.
 *
 * The dashboard below is CODED, not a screenshot — see the note on `coaches` in
 * src/content/site.ts. It is the only product visual on this site that is not a
 * real capture, and it is honest only while the page says early access.
 *
 * Surfaces run dark → light → dark → light, so this page alternates on its own
 * and does not depend on where it sits in the nav.
 */
export default function CoachesPage() {
  const { dash } = coaches;

  return (
    <>
      {/* 1 — hero */}
      <section className="section surface-dark">
        {/* container and text-col must NEST. Combined on one element the
            container itself becomes 720px and centres, indenting the hero away
            from every section below it. */}
        <div className="container">
          <div className="text-col">
          <span className="eyebrow">{coaches.eyebrow}</span>
          <h1 className="h1" style={{ fontSize: "clamp(32px, 5vw, 50px)", marginTop: "var(--s4)" }}>{coaches.h1}</h1>
          <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{coaches.sub}</p>
          <ul className="chip-row" style={{ marginTop: "var(--s5)" }} aria-label="What this is">
            {coaches.chips.map((c) => <li key={c} className="chip">{c}</li>)}
          </ul>
          </div>
        </div>
      </section>

      {/* 2 — three points */}
      <section className="section surface-light" aria-labelledby="cp-h">
        <div className="container">
          <div className="section-head">
            <h2 id="cp-h" className="h2 balance">{coaches.points.h2}</h2>
            <p className="body muted-txt">{coaches.points.sub}</p>
          </div>
          <ol className="coach-points">
            {coaches.points.items.map((pt) => (
              <li key={pt.n}>
                <span className="coach-points__n" aria-hidden>{pt.n}</span>
                <h3 className="h4">{pt.h}</h3>
                <p className="small muted-txt">{pt.p}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 3 — the dashboard */}
      <section className="section surface-dark" aria-labelledby="cd-h">
        <div className="container">
          <div className="section-head">
            <span className="coach-badge">{dash.badge}</span>
            <h2 id="cd-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{dash.h2}</h2>
            <p className="body muted-txt">{dash.sub}</p>
          </div>

          <Reveal className="dash">
            <div className="dash__top">
              <b>{dash.team}</b>
              <span>{dash.week}</span>
            </div>

            <ul className="dash__metrics">
              {dash.metrics.map((m) => (
                <li key={m.label}>
                  <span className="dash__label">{m.label}</span>
                  <b className="dash__value">
                    {m.value}{m.suffix && <span className="dash__suffix">{m.suffix}</span>}
                  </b>
                  <span className="dash__bar" aria-hidden>
                    <i className={m.warn ? "is-warn" : undefined} style={{ width: `${m.pct}%` }} />
                  </span>
                  <span className="dash__note">{m.note}</span>
                </li>
              ))}
            </ul>

            <ol className="dash__week" aria-label="The week as scheduled">
              {dash.days.map((d) => (
                <li key={d.d} className={d.game ? "is-game" : d.train ? "is-train" : undefined}>
                  <b>{d.d}</b>{d.k}
                </li>
              ))}
            </ol>

            <p className="dash__privacy">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>
              <span><strong>{dash.privacy.h}</strong> {dash.privacy.p}</span>
            </p>
          </Reveal>
        </div>
      </section>

      {/* 4 — the ask */}
      <section className="section surface-light" aria-labelledby="cf-h">
        <div className="container">
          <div className="section-head">
            <h2 id="cf-h" className="h2 balance">{coaches.form.h2}</h2>
            <p className="body muted-txt">{coaches.form.sub}</p>
          </div>
          <CoachForm />
        </div>
      </section>
    </>
  );
}
