import { Shot } from "@/components/ui/Shot";
import { Tick } from "@/components/ui/Icons";
import { dietitian } from "@/content/site";

/**
 * "A real dietitian, when the app isn't enough."
 *
 * The billing line is not a disclaimer and must never be styled as one: the app
 * charges per session, and /pricing says nothing is held back for a higher plan.
 * Naming the exception in the same block as the offer is what keeps both true.
 *
 * Light surface since 2026-08-28. Four sections were cut from the homepage that
 * day and the last four left standing were all dark, so the bottom half of the
 * page had become one unbroken dark field. This is the break in that run — the
 * section is about reaching a person, which the light surface suits. Its
 * internals were already written against light tokens (--forest ticks, --muted
 * body, a --page billing card), so the flip also fixed contrast that was wrong
 * on dark rather than introducing anything new.
 */
export function Dietitian() {
  return (
    <section id="dietitian" className="section surface-light diet" aria-labelledby="dt-h">
      <div className="container diet__grid">
        <div className="diet__copy">
          <span className="eyebrow">{dietitian.eyebrow}</span>
          <h2 id="dt-h" className="h2 balance" style={{ marginTop: "var(--s3)" }}>{dietitian.h2}</h2>
          <p className="body muted-txt" style={{ marginTop: "var(--s4)" }}>{dietitian.body}</p>

          <ul className="diet__points">
            {dietitian.points.map((p) => (
              <li key={p.h}>
                <Tick className="tick" width={18} height={18} />
                <span>
                  <strong>{p.h}</strong>
                  <span className="diet__pp">{p.p}</span>
                </span>
              </li>
            ))}
          </ul>

          <p className="diet__billing">{dietitian.billing}</p>

          {/* The waitlist button that sat here was removed on 2026-08-28 —
              one of five on the homepage. It was also the most misleading of
              them: this section sells a paid 1:1 session, and a "Join the
              waitlist" button directly under the billing line invited a reader
              to think they were signing up for the session. The waitlist form
              has its own 1:1 checkbox, which is the honest route in. */}
        </div>

        <div className="diet__shot">
          <Shot
            src="/screens/coach.webp"
            w={792}
            h={1130}
            alt="The Fuel Coach screen: an AI coach for everyday questions, and beneath it a card reading Talk to a dietitian — get a 1:1 session with a registered dietitian"
          />
        </div>
      </div>
    </section>
  );
}
