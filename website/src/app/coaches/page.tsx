import { Reveal } from "@/components/ui/Reveal";
import { CoachHeroCta } from "./CoachHeroCta";
import { CoachDash } from "./CoachDash";
import { CoachForm } from "./CoachForm";
import { Tick } from "@/components/ui/Icons";
import { coaches } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "For coaches",
  description:
    "See whether your squad is fueling for the week you planned. AthFuelPath gives coaches and athletic directors a team-level view, with nothing to set up and no individual athlete data.",
  path: "/coaches",
  image: "/og/coaches.jpg",
  imageAlt: "AthFuelPath for coaches — a team-level view of how the squad is fueling.",
});

/**
 * Coaches Corner.
 *
 * Narrative order is load-bearing: problem → low effort → value → product →
 * trust → action. A coach should be able to answer "what do I get, how much
 * work is it, what can I see about a kid, and what do I do next" inside half a
 * minute. Do not reorder these sections without re-testing that.
 *
 * Backgrounds run dark → light → tint → dark → light → tint → (dark footer),
 * so the page paces itself and does not depend on where it sits in the nav.
 *
 * The dashboard is coded, not captured. See the note on `coaches` in site.ts.
 */
export default function CoachesPage() {
  const { hero, effort, why, bridge, trust, form } = coaches;

  const icons: Record<string, React.ReactNode> = {
    calendar: (<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>),
    trend: (<><path d="M3 17l6-6 4 4 8-8" /><path d="M21 7v6h-6" /></>),
    whistle: (<><circle cx="9" cy="14" r="6" /><path d="M15 12h6M15 12l3-4" /></>),
  };

  return (
    <div className="coachpg">
      {/* 1 — hero: the problem a coach cannot see */}
      <section className="section surface-dark coach-hero">
        <div className="container">
          <div className="coach-hero__col">
            <span className="eyebrow">{hero.eyebrow}</span>
            <h1 className="coach-hero__h1">{hero.h1}</h1>
            <p className="coach-hero__lead">{hero.p1}</p>
            <p className="coach-hero__sub">{hero.p2}</p>
            <ul className="chip-row coach-hero__chips" aria-label="What this is">
              {hero.chips.map((c) => <li key={c} className="chip">{c}</li>)}
            </ul>
            <CoachHeroCta />
          </div>
        </div>
      </section>

      {/* 2 — how little work it is */}
      <section className="section surface-light" aria-labelledby="ce-h">
        <div className="container">
          <div className="section-head">
            <h2 id="ce-h" className="h2 balance">{effort.h2}</h2>
            <p className="body muted-txt">{effort.sub}</p>
          </div>
          <ol className="coach-cards">
            {effort.items.map((it) => (
              <li key={it.n} className="coach-card">
                <span className="coach-card__n" aria-hidden>{it.n}</span>
                <h3 className="coach-card__h">{it.h}</h3>
                <p className="coach-card__p">{it.p}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 3 — what the coach actually gains */}
      <section className="section surface-tint" aria-labelledby="cw-h">
        <div className="container">
          <div className="section-head">
            <h2 id="cw-h" className="h2 balance">{why.h2}</h2>
            <p className="body muted-txt">{why.sub}</p>
          </div>
          <ul className="coach-why">
            {why.items.map((it) => (
              <li key={it.h}>
                <span className="coach-why__ico" aria-hidden>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    {icons[it.icon]}
                  </svg>
                </span>
                <h3 className="h4">{it.h}</h3>
                <p className="small muted-txt">{it.p}</p>
              </li>
            ))}
          </ul>

          <p className="coach-bridge">
            <span>{bridge.a}</span>
            <span>{bridge.b}</span>
          </p>
        </div>
      </section>

      {/* 4 — the product */}
      <CoachDash />

      {/* 5 — trust */}
      <section className="section surface-light" aria-labelledby="ct-h">
        <div className="container">
          <div className="section-head">
            <h2 id="ct-h" className="h2 balance">{trust.h2}</h2>
            <p className="body muted-txt">{trust.sub}</p>
          </div>
          <ul className="coach-trust">
            {trust.items.map((it) => (
              <li key={it.h}>
                <Tick className="tick" width={18} height={18} />
                <span>
                  <strong>{it.h}</strong>
                  <span className="coach-trust__p">{it.p}</span>
                </span>
              </li>
            ))}
          </ul>

          <Reveal className="coach-cred" i={1}>
            <span className="eyebrow">{trust.credibility.label}</span>
            <p className="coach-cred__p">{trust.credibility.p}</p>
            <p className="coach-cred__who">
              <strong>{trust.credibility.name}</strong>
              <span>{trust.credibility.role}</span>
            </p>
          </Reveal>
        </div>
      </section>

      {/* 6 — conversion */}
      <section id="coach-access" className="section surface-tint" aria-labelledby="cf-h">
        <div className="container coach-access">
          <div>
            <h2 id="cf-h" className="h2 balance">{form.h2}</h2>
            <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{form.sub}</p>
            <p className="small muted-txt" style={{ marginTop: "var(--s4)" }}>{form.note}</p>
          </div>
          <CoachForm />
        </div>
      </section>
    </div>
  );
}
