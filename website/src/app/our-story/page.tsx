import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Arrow } from "@/components/ui/Icons";
import { ourStory, cta, trialLine } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Our story",
  description:
    "AthFuelPath was built by a Registered Dietitian whose own daughter plays competitive soccer. Knowing the nutrition was one thing; making it work around school, practices and tournament weekends was another.",
  path: "/our-story",
  image: "/og/our-story.jpg",
  imageAlt: "Purvi Shah, MS, RDN — the dietitian and soccer mom who built AthFuelPath.",
});

/**
 * Our Story — five chapters, in order: who built it, why it became personal,
 * how one family's fix became a product, what it holds to, a personal close.
 *
 * Structural rule that replaced the previous version: the two-column layout
 * ENDS with the hero. The old page ran one long text column beside the portrait
 * for the whole page, which left a tall empty gap under the photograph, and
 * stacked six biography subsections where the story should have been.
 *
 * Backgrounds use three values only — base, tint, dark — rather than six
 * near-identical whites.
 *
 * The founder quote is deliberately absent until Purvi approves the wording.
 * See `ourStory.close.quote` in site.ts; the close renders correctly either way.
 */
export default function OurStory() {
  const { hero, personal, origin, belief, close } = ourStory;

  return (
    <>
      {/* 01 — who built it */}
      <section className="section surface-light">
        <div className="container story-hero">
          {/* Source order puts the text first so mobile reads eyebrow → h1 →
              intro → portrait, giving the photograph context before it appears.
              The grid puts the portrait back on the left at desktop. */}
          <div className="story-hero__copy">
            <span className="eyebrow">{hero.eyebrow}</span>
            <h1 className="story-hero__h1">{hero.h1}</h1>
            <p className="story-hero__p">{hero.p1}</p>
            <p className="story-hero__p">{hero.p2}</p>
          </div>

          <div className="story-hero__media">
            <Image
              src="/img/purvi.webp"
              alt={hero.portraitAlt}
              width={880}
              height={1100}
              className="story-hero__portrait"
              sizes="(max-width: 900px) 92vw, 520px"
              priority
            />
            <div className="story-card">
              <Image src="/img/purvi-avatar.webp" alt="" width={192} height={192} className="story-card__ico" aria-hidden />
              <span>
                <strong>{hero.card.name}</strong>
                <span className="story-card__role">{hero.card.role}</span>
                <span className="story-card__line">{hero.card.line}</span>
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 02 — the real family problem */}
      <section className="section surface-tint" aria-labelledby="sp-h">
        <div className="container">
          <div className="story-col">
            <span className="eyebrow">{personal.eyebrow}</span>
            <h2 id="sp-h" className="story-h2">{personal.h2}</h2>
            {personal.body.map((t) => <p key={t} className="story-p">{t}</p>)}

            {/* Editorial statements, not cards. These are the parent's problem
                and the origin of the company at once, so they carry the visual
                weight of this section. */}
            <ul className="story-qs">
              {personal.questions.map((q) => <li key={q}>{q}</li>)}
            </ul>

            <p className="story-p">{personal.close1}</p>
            <p className="story-p story-p--lead">{personal.close2}</p>
          </div>
        </div>
      </section>

      {/* 03 — one family's fix becomes a product */}
      <section className="section surface-dark" aria-labelledby="so-h">
        <div className="container">
          <div className="story-col">
            <span className="eyebrow">{origin.eyebrow}</span>
            <h2 id="so-h" className="story-h2">{origin.h2}</h2>
            {origin.body.map((t) => <p key={t} className="story-p">{t}</p>)}
          </div>

          <p className="story-statement">
            <span>{origin.statement.a}</span>
            <span>{origin.statement.b}</span>
          </p>

          <p className="story-origin-link">
            <Link href={origin.link.href} className="tlink">{origin.link.label} <Arrow /></Link>
          </p>
        </div>
      </section>

      {/* 04 — what it holds to */}
      <section className="section surface-light" aria-labelledby="sb-h">
        <div className="container">
          {/* The one positioning statement on the site. Whitespace is the
              emphasis: no card, no icons, and it is never restated elsewhere. */}
          <p className="story-belief">
            <span>{belief.a}</span>
            <strong>{belief.b}</strong>
          </p>
          <p className="story-belief__sub">{belief.sub}</p>

          <div className="story-principles">
            <div className="section-head">
              <span className="eyebrow">{belief.eyebrow}</span>
              <h2 id="sb-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{belief.h2}</h2>
            </div>
            {/* Parallel convictions. Never numbered, never iconed, no sequence. */}
            <ul className="story-principles__list">
              {belief.items.map((it) => (
                <li key={it.h}>
                  <span className="story-principles__rule" aria-hidden />
                  <h3 className="story-principles__h">{it.h}</h3>
                  <p className="story-principles__p">{it.p}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* 05 — personal close */}
      <section className="section surface-tint" aria-labelledby="sc-h">
        <div className="container story-close">
          {close.quote && (
            <figure className="story-quote">
              <blockquote>{close.quote.text}</blockquote>
              <figcaption>
                <strong>{close.quote.name}</strong>
                <span>{close.quote.role}</span>
              </figcaption>
            </figure>
          )}

          <h2 id="sc-h" className="h2 balance">{close.h2}</h2>
          <p className="body muted-txt story-close__sub">{close.sub}</p>

          <div className="cta-row cta-row--center story-close__cta">
            <Button href="/signup" hero arrow section="our-story">{cta.primary}</Button>
            <Link href={close.secondary.href} className="tlink">{close.secondary.label} <Arrow /></Link>
          </div>
          <p className="trust-row">{trialLine}</p>
        </div>
      </section>
    </>
  );
}
