import { TextLink } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { safety, cta } from "@/content/site";

export function Safety() {
  return (
    <section id="for-parents" className="section surface-dark" aria-labelledby="sf-h">
      <div className="container">
        <div className="section-head section-head--center">
          <span className="eyebrow">{safety.eyebrow}</span>
          <h2 id="sf-h" className="h2 balance">{safety.h2}</h2>
        </div>
        <ul className="safety-grid">
          {safety.claims.map((c, i) => (
            <Reveal as="li" key={c.t} className="card--dark safety-card" i={((i % 3) + 1) as 1 | 2 | 3}>
              <p>{c.t}</p>
              <p>{c.d}</p>
            </Reveal>
          ))}
        </ul>
        <p style={{ marginTop: "var(--s6)", textAlign: "center" }}>
          <TextLink href="/safety" section="safety">{cta.safety}</TextLink>
        </p>
      </div>
    </section>
  );
}
