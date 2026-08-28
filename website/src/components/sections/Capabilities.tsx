import Link from "next/link";
import { Arrow } from "@/components/ui/Icons";
import { capabilities } from "@/content/site";

/**
 * An index of what is inside, not a demo.
 *
 * This replaced the "What should I cook this week?" block, which was the single
 * largest thing on the homepage — four numbered sub-sections, two phone frames,
 * chip rows and a closing strip. That block now opens /parents, where a reader
 * has already decided they are interested and will actually read it.
 *
 * GUARDRAIL, and the reason this component holds no screenshots: if a card
 * grows past roughly 280px tall, cut copy. Do not grow the card, and do not add
 * a product image inside one — that turns the index back into the demo it
 * replaced and the homepage gets long again.
 */
const ICONS: Record<string, React.ReactNode> = {
  sun: (<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>),
  bowl: (<><path d="M3 11h18a9 9 0 0 1-18 0Z" /><path d="M8 7c0-1.5 1-2 1-3M12 7c0-1.5 1-2 1-3M16 7c0-1.5 1-2 1-3" /></>),
  chat: (<><path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z" /></>),
  cart: (<><circle cx="9" cy="20" r="1.4" /><circle cx="18" cy="20" r="1.4" /><path d="M2 3h3l2.6 12.1a2 2 0 0 0 2 1.6h7.9a2 2 0 0 0 2-1.55L21 8H6" /></>),
};

export function Capabilities() {
  return (
    <section id="capabilities" className="section surface-light" aria-labelledby="cap-h">
      <div className="container">
        <div className="section-head section-head--center">
          <span className="eyebrow">{capabilities.eyebrow}</span>
          <h2 id="cap-h" className="h2 balance">{capabilities.h2}</h2>
        </div>

        <ul className="cap-grid">
          {capabilities.items.map((it) => (
            <li key={it.label} className="cap-card">
              <span className="cap-card__ico" aria-hidden>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  {ICONS[it.icon]}
                </svg>
              </span>
              <span className="cap-card__label">{it.label}</span>
              <h3 className="cap-card__h">{it.h}</h3>
              <p className="cap-card__p">{it.p}</p>
            </li>
          ))}
        </ul>

        <p className="cap-cta">
          <Link href={capabilities.cta.href} className="tlink">{capabilities.cta.label} <Arrow /></Link>
        </p>
      </div>
    </section>
  );
}
