import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Arrow } from "@/components/ui/Icons";
import { Shot } from "@/components/ui/Shot";
import { Reveal } from "@/components/ui/Reveal";
import { Accordion } from "@/components/ui/Accordion";
import { Dietitian } from "@/components/sections/Dietitian";
import { parents, cta } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Youth sports nutrition for parents: how AthFuelPath works",
  description:
    "How AthFuelPath fits a soccer family's week: one schedule to add, guidance your athlete can follow themselves, recipes that respect their allergies, and a registered dietitian when you need one.",
  path: "/parents",
  image: "/og/home.jpg",
  imageAlt: "AthFuelPath for parents — fueling built around your athlete's schedule.",
});

/**
 * /parents — the CONSIDERATION page.
 *
 * The homepage does recognition. This page is for the parent who is already
 * interested and is now looking for a reason to say no, and it answers those
 * five objections in order: is this another app to run, will my athlete use it,
 * is it right for a 14-year-old, what about her allergy, can I trust this.
 *
 * THE RULE THAT KEEPS IT HONEST: no section here may be a second copy of a
 * homepage module. Two pages with the same H2 and the same block compete for
 * the same query and read as padding. Where a concept appears on both, the
 * version here is shorter or deeper, differently headlined, and linked.
 *   - schedule: homepage owns the full module with the weekly UI. Here it is a
 *     three-step bridge with no schedule UI at all.
 *   - safety:   homepage has a three-point strip, this has four cards with the
 *     Fuel Coach disclosure, /safety has the complete account.
 *   - dietitian and the recipe/grocery block were REMOVED from the homepage, so
 *     they are not duplicated — they only live here now.
 *
 * Background rhythm is light → tint → dark, cycling. Three tokens, matching the
 * rest of the site. The spec asked for Light/White/Dark, which is four values;
 * "white" maps onto the existing tint band rather than introducing a fourth.
 */
export default function Parents() {
  const { hero, lead, schedule, independence, table, person, safe, faq, close } = parents;

  return (
    <>
      {/* 01 — hero */}
      <section className="section surface-light">
        <div className="container par-hero">
          <div className="par-hero__copy">
            <span className="eyebrow">{hero.eyebrow}</span>
            <h1 className="par-hero__h1">{hero.h1}</h1>
            <p className="par-hero__p">{hero.p}</p>
            <div className="cta-row par-hero__cta">
              <Button href="/signup" hero arrow section="parents-hero">{cta.primary}</Button>
              <Link href={hero.secondary.href} className="tlink">{hero.secondary.label} <Arrow /></Link>
            </div>
          </div>
          {/* The product screenshot is the credibility on this page. No stock
              soccer photography anywhere on it. */}
          <div className="par-hero__shot">
            <Shot
              src="/screens/today.png"
              w={792}
              h={1600}
              alt="The Today screen: the day's eating windows laid out around a 5:30 practice"
            />
          </div>
        </div>
      </section>

      {/* 02 — the page's lead. Deliberately something the homepage lacks. */}
      <section className="section surface-tint" aria-labelledby="pl-h">
        <div className="container">
          <div className="section-head section-head--center">
            <span className="eyebrow">{lead.eyebrow}</span>
            <h2 id="pl-h" className="h2 balance">{lead.h2}</h2>
            <p className="body muted-txt">{lead.p}</p>
          </div>
          <ul className="par-moments">
            {lead.moments.map((m) => (
              <li key={m.when}>
                <span className="par-moments__when">{m.when}</span>
                <p className="par-moments__q">{m.q}</p>
              </li>
            ))}
          </ul>
          {/* No CTA here on purpose — the page has barely started its argument. */}
          <p className="par-lead__close">{lead.close}</p>
        </div>
      </section>

      {/* 03 — a bridge, not a section. The homepage owns the schedule module. */}
      <section className="section surface-dark" aria-labelledby="ps-h">
        <div className="container">
          <h2 id="ps-h" className="h2 balance par-bridge__h">{schedule.h2}</h2>
          <p className="par-flow" aria-hidden>
            {schedule.flow.map((f, i) => (
              <span key={f}>
                {f}
                {i < schedule.flow.length - 1 && <span className="par-flow__arw">→</span>}
              </span>
            ))}
          </p>
          <ol className="par-steps">
            {schedule.steps.map((s, i) => (
              <li key={s.h}>
                <span className="par-steps__n" aria-hidden>{`0${i + 1}`}</span>
                <h3 className="par-steps__h">{s.h}</h3>
                <p className="par-steps__p">{s.p}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 04 — the section the homepage cannot carry: will I have to run this? */}
      <section className="section surface-light" aria-labelledby="pi-h">
        <div className="container par-split par-split--reverse">
          {/* Phone on the LEFT here, opposite to every other split on the page,
              so a long page has some rhythm rather than one repeated shape. */}
          <div className="par-split__shot">
            <Shot
              src="/screens/plate.webp"
              w={792}
              h={1600}
              alt="The athlete's own view of the day, showing what to eat and when without a parent prompting them"
            />
          </div>
          <div>
            <span className="eyebrow">{independence.eyebrow}</span>
            <h2 id="pi-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{independence.h2}</h2>
            <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{independence.p}</p>
            {/* Growing independence, never a curriculum: no progress bars, no
                levels, no education framing on a marketing page. */}
            <ol className="par-stages">
              {independence.stages.map((s) => (
                <li key={s.n}>
                  <span className="par-stages__n" aria-hidden>{s.n}</span>
                  <span>{s.t}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* 05 — migrated off the homepage: recipes and the grocery list */}
      <section className="section surface-dark" aria-labelledby="pt-h">
        {/* Stacked, not a split. The two phone frames are a fixed 300px each,
            so a 42% column could not hold them at any width below ~1500 and
            they pushed the page 79px wide at 1024. Copy above, both frames
            centred beneath at full container width — which is also where the
            spec wants them "rendered slightly larger". */}
        <div className="container par-stack">
          <div>
            <span className="eyebrow">{table.eyebrow}</span>
            <h2 id="pt-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{table.h2}</h2>
            <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{table.p}</p>
            <ol className="par-points">
              {table.points.map((p) => (
                <li key={p.n}>
                  <span className="par-points__n" aria-hidden>{p.n}</span>
                  <h3 className="par-points__h">{p.h}</h3>
                  <p className="par-points__p">{p.p}</p>
                </li>
              ))}
            </ol>
          </div>
          <div className="par-shots">
            <Shot
              src="/screens/mealplan-choose.png"
              w={792}
              h={1600}
              alt="Filling one lunch window: a covered option, a box to describe your own dish, then the recipes to pick from"
            />
            <Shot
              src="/screens/grocery.webp"
              w={786}
              h={1600}
              className="device--b"
              alt="The grocery list it produced, grouped into produce, protein, carbs and grains, each item labelled with the recipe it came from"
            />
          </div>
        </div>
      </section>

      {/* 06 — migrated off the homepage: the dietitian. Same component, its own
          headline, so the two pages never rendered the same module. */}
      <Dietitian head={{ eyebrow: person.eyebrow, h2: person.h2, p: person.p }} />

      {/* 07 — the strongest trust section on the site */}
      <section id="safety" className="section surface-dark" aria-labelledby="psf-h">
        <div className="container">
          <div className="section-head section-head--center">
            <span className="eyebrow">{safe.eyebrow}</span>
            <h2 id="psf-h" className="h2 balance">{safe.h2}</h2>
          </div>
          <ul className="par-safe">
            {safe.cards.map((c, i) => (
              <Reveal as="li" key={c.h} className="card--dark" i={((i % 3) + 1) as 1 | 2 | 3}>
                <h3 className="par-safe__h">{c.h}</h3>
                <p className="par-safe__p">{c.p}</p>
              </Reveal>
            ))}
          </ul>
          <p className="par-safe__note">
            <strong>{safe.note.h}</strong> {safe.note.p}
          </p>
          <p className="par-safe__link">
            <Link href={safe.link.href} className="tlink">{safe.link.label} <Arrow /></Link>
          </p>
        </div>
      </section>

      {/* 08 — the objections, answered plainly */}
      <section className="section surface-tint" aria-labelledby="pf-h">
        <div className="container">
          <div className="text-col">
            <span className="eyebrow">{faq.eyebrow}</span>
            <h2 id="pf-h" className="h2 balance" style={{ marginTop: "var(--s3)", marginBottom: "var(--s5)" }}>{faq.h2}</h2>
            <Accordion items={faq.items} openFirst />
          </div>
        </div>
      </section>

      {/* 09 — same component shape as the homepage close, different headline */}
      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">{close.h2}</h2>
          <p className="body muted-txt">{close.sub}</p>
          <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
            <Button href="/signup" hero arrow section="parents-final">{cta.primary}</Button>
          </div>
          <p className="trust-row">{close.trust}</p>
        </div>
      </section>
    </>
  );
}
