import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Arrow } from "@/components/ui/Icons";
import { Reveal } from "@/components/ui/Reveal";
import { FuelIq } from "./FuelIq";
import { Clock, Whistle, Recover, Calendar, Drop, Spark, Flag, Plate, Check } from "./icons";
import { athletes, cta } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "For athletes: know how to fuel your day",
  description:
    "AthFuelPath tells you what to eat and when, around your own practices and games. FuelIQ turns sports nutrition into short challenges so you learn why it works. For athletes 13–17.",
  path: "/athletes",
  imageAlt: "AthFuelPath for athletes — fuel for what's next.",
});

/**
 * /athletes — the page the athlete reads.
 *
 * BUILT TO ITS OWN DESIGN SPEC, and that spec is not the rest of the site's.
 * It adds a fourth surface (dim #D8DBD6), two accents (carbs, sodium) and two
 * mid greens the site does not otherwise have. Everything it introduces is
 * scoped to the `.ath` wrapper below, so this page can take the spec without
 * dragging 20 other pages into a palette nobody asked to change. Six of the
 * spec's tokens were already site tokens byte for byte and are reused.
 *
 * The one value NOT taken from the spec is muted-foreground. See the note above
 * the .ath block in globals.css: #707973 fails WCAG AA on all three of the
 * spec's own surfaces, worst of all on the dim band it introduces.
 *
 * ROUTE NAME. /athletes, not /for-athletes, matching /parents. /for-athletes
 * 308s here, like the /for-parents redirect that exists because that prefix was
 * a mistake once already.
 *
 * WHAT THIS PAGE IS FOR: a 13-year-old cannot join the waitlist — the form
 * collects a parent's name and email and a parent controls the account. So the
 * job is advocacy, not conversion: give the athlete the words to ask a parent,
 * and give the parent reading over their shoulder a reason to say yes.
 *
 * THE DUPLICATION RULE, same as /parents. Two sections come close to restating
 * another page and are deliberately short and linked — independence belongs to
 * /parents, safety belongs to /safety. If either grows, cut it.
 */

/* Icons paired to content by position. Kept beside the page rather than in
   site.ts, because site.ts holds copy and these are not copy. */
const NUDGE_ICONS = [Clock, Whistle, Recover, Calendar];
const TOPIC_ICONS = [Drop, Spark, Flag, Plate, Check];

export default function Athletes() {
  const { hero, reminders, topics, independence, progress, trust, close } = athletes;

  return (
    <div className="ath">
      {/* 02 — hero. Centred, 880px, text only. Every other hero on the site
          carries a phone frame; the screen worth showing here is FuelIQ, two
          sections down, where it has three of its own. */}
      <section className="section surface-light">
        <div className="container">
          <div className="ath-hero">
            <span className="eyebrow">{hero.eyebrow}</span>
            <h1 className="ath-hero__h1">{hero.h1}</h1>
            <p className="ath-hero__p">{hero.p}</p>
            <div className="cta-row ath-hero__cta">
              <Button href="/signup" hero arrow section="athletes_hero">{cta.primary}</Button>
              <Link href={hero.secondary.href} className="tlink">{hero.secondary.label} <Arrow /></Link>
            </div>
          </div>
        </div>
      </section>

      {/* 03 — nudges */}
      <section className="section surface-tint" aria-labelledby="ar-h">
        <div className="container">
          <div className="section-head section-head--center">
            <span className="eyebrow">{reminders.eyebrow}</span>
            <h2 id="ar-h" className="h2 balance">{reminders.h2}</h2>
            <p className="body muted-txt">{reminders.p}</p>
          </div>
          <ul className="ath-notes">
            {reminders.cards.map((c, i) => {
              const Icon = NUDGE_ICONS[i];
              return (
                <Reveal as="li" key={c.when} className="ath-card-base ath-note" i={((i % 3) + 1) as 1 | 2 | 3}>
                  <span className="ath-note__badge"><Icon /></span>
                  <b className="ath-note__when">{c.when}</b>
                  <p className="ath-note__body">{c.body}</p>
                </Reveal>
              );
            })}
          </ul>
          {/* Restraint stated as a feature. This is the line a parent reads. */}
          <p className="ath-notes__note">{reminders.note}</p>
        </div>
      </section>

      {/* 04 — FuelIQ, the centrepiece */}
      <FuelIq />

      {/* 05 — build your Fuel IQ */}
      <section className="section surface-light" aria-labelledby="at-h">
        <div className="container">
          <div className="section-head section-head--center">
            <span className="eyebrow">{topics.eyebrow}</span>
            <h2 id="at-h" className="h2 balance">{topics.h2}</h2>
            <p className="body muted-txt">{topics.p}</p>
          </div>
          <ul className="ath-topics">
            {topics.items.map((t, i) => {
              const Icon = TOPIC_ICONS[i];
              return (
                <li key={t.h} className="ath-card-base">
                  <span className="ath-topics__chip"><Icon /></span>
                  <h3 className="ath-topics__h">{t.h}</h3>
                  <p className="ath-topics__p">{t.p}</p>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* 06 — understand it. SHORT — /parents owns this argument in full.
          This was two columns: headline left, everything else right. The left
          column ran out after the headline and left 119x552px of nothing under
          it — the same mismatched-column void that had to be fixed on the Our
          Story hero and the /parents hero. Centred header over a full-width
          progression, so there is no short column to leave a hole.

          The four steps are the section's actual argument and used to be its
          least visible element: four words in a small uppercase strip. A
          sequence should look like a sequence. */}
      <section className="section surface-tint" aria-labelledby="ai-h">
        <div className="container">
          <div className="section-head section-head--center ath-ind__head">
            <span className="eyebrow">{independence.eyebrow}</span>
            <h2 id="ai-h" className="h2 balance">{independence.h2}</h2>
            <p className="body muted-txt">{independence.p}</p>
          </div>

          {/* An ordered list, because it is one. The connecting rule is drawn
              with a pseudo-element and hidden from assistive tech — the <ol>
              already says these are ordered. */}
          <ol className="ath-steps">
            {independence.steps.map((s, i) => (
              <Reveal as="li" key={s.t} className="ath-steps__i" i={((i % 3) + 1) as 1 | 2 | 3}>
                <span className="ath-steps__n" aria-hidden>{s.n}</span>
                <h3 className="ath-steps__t">{s.t}</h3>
                <p className="ath-steps__p">{s.p}</p>
              </Reveal>
            ))}
          </ol>

          <p className="ath-ind__close">{independence.close}</p>
          <p className="ath-ind__link">
            <Link href={independence.link.href} className="tlink">{independence.link.label} <Arrow /></Link>
          </p>
        </div>
      </section>

      {/* 07 — Fuel IQ over time */}
      <section className="section surface-light" aria-labelledby="ap-h">
        <div className="container ath-prog">
          <div>
            <span className="eyebrow">{progress.eyebrow}</span>
            <h2 id="ap-h" className="h2 balance" style={{ marginTop: "var(--s2)" }}>{progress.h2}</h2>
            <p className="body muted-txt" style={{ marginTop: "14px", fontSize: "15px" }}>{progress.p}</p>
            <p className="ath-prog__strong">{progress.strongest}</p>
          </div>
          {/* Inert markup: nothing focusable and no progressbar role. This is a
              picture of progress, not anyone's real record. */}
          <div className="ath-card">
            <span className="eyebrow ath-card__lab">Fuel IQ</span>
            <b className="ath-card__lvl">{progress.level}</b>
            <div className="ath-card__bar" aria-hidden>
              <span style={{ width: `${progress.fill}%` }} />
            </div>
            <div className="ath-week" aria-hidden>
              {progress.week.map((d, i) => (
                <span key={i} className={`ath-week__d is-${d}`} />
              ))}
            </div>
            <span className="ath-card__note">{progress.weekNote}</span>
          </div>
        </div>
      </section>

      {/* 08 — promise cards. SHORT — /safety owns the full account. */}
      <section className="section surface-tint" aria-labelledby="asf-h">
        <div className="container">
          <div className="section-head section-head--center">
            <h2 id="asf-h" className="h2 balance">{trust.h2}</h2>
            <p className="body muted-txt">{trust.p}</p>
          </div>
          <ul className="ath-trust">
            {trust.points.map((p) => (
              <li key={p.h}>
                <h3 className="ath-trust__h">{p.h}</h3>
                <p className="ath-trust__p">{p.p}</p>
              </li>
            ))}
          </ul>
          <p className="ath-trust__link">
            <Link href={trust.link.href} className="tlink">{trust.link.label} <Arrow /></Link>
          </p>
        </div>
      </section>

      {/* 09 — final CTA. The waitlist stays primary because a parent is often
          the one holding the phone; the secondary is the action that actually
          fits the reader. */}
      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">{close.h2}</h2>
          <p className="body muted-txt">{close.sub}</p>
          <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
            <Button href="/signup" hero arrow section="athletes_final">{cta.primary}</Button>
            <Link href={close.secondary.href} className="tlink">{close.secondary.label} <Arrow /></Link>
          </div>
          <p className="trust-row">{close.trust}</p>
        </div>
      </section>
    </div>
  );
}
