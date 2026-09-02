import { Reveal } from "@/components/ui/Reveal";
import { Shot } from "@/components/ui/Shot";
import { athletes } from "@/content/site";

/**
 * The FuelIQ section: three real captures from the app, with the argument they
 * make written beside each one.
 *
 * These three screens were drawn in markup first, because FuelIQ had not
 * shipped and there was nothing to photograph that would still be accurate on
 * the day it did. The captures arrived, so the drawing is deleted rather than
 * kept around — its whole justification was the absence of these files, and a
 * second version of a component nobody renders is how a codebase starts lying
 * about itself. Same for the .fqs CSS block that styled it.
 *
 * SERVER COMPONENT. Three images and their captions need no state.
 *
 * The order is the argument: a real question, then the reasoning, then the
 * progress. Putting XP first would make this a game with nutrition attached,
 * which is the one thing this section exists not to be.
 */

const { fueliq } = athletes;

export function FuelIq() {
  return (
    <section id="fueliq" className="section surface-dark" aria-labelledby="fq-h">
      <div className="container">
        <div className="section-head section-head--center">
          <span className="eyebrow">{fueliq.eyebrow}</span>
          <h2 id="fq-h" className="h2 balance">
            {fueliq.h2} <span className="fq__sub">{fueliq.sub}</span>
          </h2>
          <p className="body muted-txt">{fueliq.p}</p>
        </div>

        <ol className="fq">
          {fueliq.steps.map((s, i) => {
            const shot = fueliq.shots[i];
            return (
              <Reveal as="li" key={s.n} className="fq__step" i={((i % 3) + 1) as 1 | 2 | 3}>
                {/* Screen first, caption second. On a page whose whole claim is
                    "this is a real product", the capture is the evidence and the
                    words are the caption. */}
                <div className="fq__screen">
                  <Shot src={shot.src} w={shot.w} h={shot.h} alt={shot.alt} />
                </div>
                <div className="fq__copy">
                  <span className="fq__n" aria-hidden>{s.n}</span>
                  {/* .eyebrow because that is what these are: the class carries
                      the site's micro-label size and its documented exemption
                      from the 15px type floor. */}
                  <span className="eyebrow fq__label">{s.label}</span>
                  <h3 className="fq__h">{s.h}</h3>
                  <p className="fq__p">{s.p}</p>
                  <span className="fq__meta">{s.meta}</span>
                </div>
              </Reveal>
            );
          })}
        </ol>

        {/* Learn → Understand → Practice → Progress. Decorative: the numbered
            steps above already carry the same order, so a screen reader that
            has just read them does not need it twice. */}
        <p className="fq__flow" aria-hidden>
          {fueliq.flow.map((f, i) => (
            <span key={f}>
              {f}
              {i < fueliq.flow.length - 1 && <span className="fq__arw">→</span>}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}
