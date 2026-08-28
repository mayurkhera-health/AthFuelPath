import Link from "next/link";
import { Reveal } from "@/components/ui/Reveal";
import { Arrow } from "@/components/ui/Icons";
import { safety } from "@/content/site";

/**
 * Trust strip. Compressed from a six-claim section to three short points.
 *
 * It stays on the homepage on purpose. For a nutrition product aimed at minors,
 * "is this a diet app in disguise" is a first-thirty-seconds objection, not a
 * consideration-stage one — so the shortest version of the answer belongs
 * where a cold visitor meets it. The fuller version is /parents#safety and the
 * complete account is /safety. Three depths, each linked to the next.
 *
 * Cards must not exceed ~160px. If a claim needs more room than that, it
 * belongs on one of the other two pages, not here.
 */
export function Safety() {
  return (
    <section id="for-parents" className="section surface-dark" aria-labelledby="sf-h">
      <div className="container">
        <div className="section-head section-head--center">
          <span className="eyebrow">{safety.eyebrow}</span>
          <h2 id="sf-h" className="h2 balance">{safety.h2}</h2>
          <p className="body muted-txt">{safety.sub}</p>
        </div>
        <ul className="safety-grid">
          {safety.claims.map((c, i) => (
            <Reveal as="li" key={c.t} className="card--dark safety-card" i={((i % 3) + 1) as 1 | 2 | 3}>
              <p>{c.t}</p>
              <p>{c.d}</p>
            </Reveal>
          ))}
        </ul>

        <p className="safety-secondary">{safety.secondary}</p>

        <p className="safety-links">
          {safety.links.map((l) => (
            <Link key={l.href} href={l.href} className="tlink">{l.label} <Arrow /></Link>
          ))}
        </p>
      </div>
    </section>
  );
}
