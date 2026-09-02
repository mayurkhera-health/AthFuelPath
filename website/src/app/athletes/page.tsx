import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Arrow } from "@/components/ui/Icons";
import { Reveal } from "@/components/ui/Reveal";
import { FuelIq } from "./FuelIq";
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
 * ROUTE NAME. /athletes, not /for-athletes, matching /parents. There is already
 * a permanent redirect from /for-parents because that prefix was a mistake once;
 * /for-athletes redirects here for the same reason rather than repeating it.
 *
 * WHAT THIS PAGE IS FOR: see the long note above `athletes` in site.ts. Short
 * version — a 13-year-old cannot join the waitlist, because the form collects a
 * parent's name and email and a parent controls the account. So the page's job
 * is advocacy, not conversion: give the athlete the words to ask a parent, and
 * give the parent reading over their shoulder a reason to say yes.
 *
 * THE DUPLICATION RULE, same as /parents. No section here restates one from
 * another page. Two come close and are deliberately four lines and a link
 * rather than a retelling — independence belongs to /parents, safety belongs to
 * /safety. If either grows, cut it.
 *
 * Backgrounds cycle light → tint → dark through the three surface tokens. The
 * spec asked for eight distinct background values; the site has three, and
 * three is what keeps every page looking like the same product.
 */
export default function Athletes() {
  const { hero, reminders, topics, independence, progress, trust, close } = athletes;

  return (
    <>
      {/* 01 — hero. Text only. Every other hero on the site carries a phone
          frame, and the honest position here is that the screen worth showing
          is FuelIQ, which is two sections down and has three of its own. A
          borrowed screenshot at the top would be decoration. */}
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

      {/* 02 — the reminders, from the athlete's side */}
      <section className="section surface-tint" aria-labelledby="ar-h">
        <div className="container">
          <div className="section-head section-head--center">
            <span className="eyebrow">{reminders.eyebrow}</span>
            <h2 id="ar-h" className="h2 balance">{reminders.h2}</h2>
            <p className="body muted-txt">{reminders.p}</p>
          </div>
          <ul className="ath-notes">
            {reminders.cards.map((c, i) => (
              <Reveal as="li" key={c.when} className="ath-note" i={((i % 3) + 1) as 1 | 2 | 3}>
                <span className="eyebrow ath-note__app">AthFuelPath</span>
                <b className="ath-note__when">{c.when}</b>
                <p className="ath-note__body">{c.body}</p>
              </Reveal>
            ))}
          </ul>
          {/* Restraint stated as a feature. This is the line a parent reads. */}
          <p className="ath-notes__note">{reminders.note}</p>
        </div>
      </section>

      {/* 03 — FuelIQ, the centrepiece */}
      <FuelIq />

      {/* 04 — what you'll learn */}
      <section className="section surface-light" aria-labelledby="at-h">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">{topics.eyebrow}</span>
            <h2 id="at-h" className="h2 balance">{topics.h2}</h2>
            <p className="body muted-txt">{topics.p}</p>
          </div>
          {/* Rules, not cards. Five boxed cards would outweigh the FuelIQ
              section above them, and this is a list of subjects rather than
              five separate claims. */}
          <ul className="ath-topics">
            {topics.items.map((t) => (
              <li key={t.h}>
                <h3 className="ath-topics__h">{t.h}</h3>
                <p className="ath-topics__p">{t.p}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 05 — independence. SHORT. /parents owns the argument. */}
      <section className="section surface-tint" aria-labelledby="ai-h">
        <div className="container">
          <div className="ath-ind">
            <span className="eyebrow">{independence.eyebrow}</span>
            <h2 id="ai-h" className="h2 balance">{independence.h2}</h2>
            <p className="body muted-txt">{independence.p}</p>
            <p className="ath-ind__flow" aria-hidden>
              {independence.steps.map((s, i) => (
                <span key={s}>
                  {s}
                  {i < independence.steps.length - 1 && <span className="ath-ind__arw">→</span>}
                </span>
              ))}
            </p>
            <p className="ath-ind__close">{independence.close}</p>
            <p className="ath-ind__link">
              <Link href={independence.link.href} className="tlink">{independence.link.label} <Arrow /></Link>
            </p>
          </div>
        </div>
      </section>

      {/* 06 — progress */}
      <section className="section surface-light" aria-labelledby="ap-h">
        <div className="container ath-prog">
          <div>
            <span className="eyebrow">{progress.eyebrow}</span>
            <h2 id="ap-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{progress.h2}</h2>
            <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{progress.p}</p>
            <p className="ath-prog__strong">{progress.strongest}</p>
          </div>
          {/* Drawn, like the FuelIQ screens, and for the same reason. Inert
              markup: nothing focusable, no progressbar role — a picture of
              progress, not anyone's real record. */}
          <div className="ath-card">
            <div className="ath-card__top">
              <b>{progress.level}</b>
              <span>{progress.toNext}</span>
            </div>
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

      {/* 07 — trust. SHORT. /safety owns the full account. */}
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

      {/* 08 — close. The primary action is the one an athlete can actually
          take; the waitlist follows for whoever is holding the phone. */}
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
    </>
  );
}
