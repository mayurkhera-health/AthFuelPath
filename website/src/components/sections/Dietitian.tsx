import { Shot } from "@/components/ui/Shot";
import { Button } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { dietitian } from "@/content/site";

/**
 * "A real dietitian, when the app isn't enough."
 *
 * The billing line is not a disclaimer and must never be styled as one: the app
 * charges per session, and /pricing says nothing is held back for a higher plan.
 * Naming the exception in the same block as the offer is what keeps both true.
 */
export function Dietitian() {
  return (
    <section id="dietitian" className="section surface-dark diet" aria-labelledby="dt-h">
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

          <div className="cta-row" style={{ marginTop: "var(--s5)" }}>
            <Button href="/signup" arrow section="dietitian">{dietitian.cta}</Button>
          </div>
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
