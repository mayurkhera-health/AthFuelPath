import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { steps, cta } from "@/content/site";

export function Steps() {
  return (
    <section id="how-it-works" className="section surface-light" aria-labelledby="st-h">
      <div className="container">
        <div className="section-head section-head--center">
          <span className="eyebrow">{steps.eyebrow}</span>
          <h2 id="st-h" className="h2 balance">{steps.h2}</h2>
          <p className="body muted-txt">{steps.sub}</p>
        </div>
        <ol className="grid grid-3">
          {steps.items.map((s, i) => (
            <Reveal as="li" key={s.n} className="card" i={((i % 3) + 1) as 1 | 2 | 3}>
              <span className="step__num" aria-hidden>{s.n}</span>
              <h3 className="h4" style={{ marginTop: "var(--s3)" }}>{s.title}</h3>
              <p className="small muted-txt" style={{ marginTop: "var(--s2)", fontSize: 18 }}>{s.body}</p>
              <ul className="chip-row" style={{ marginTop: "var(--s4)" }}>
                {s.chips.map((c) => <li key={c} className="chip">{c}</li>)}
              </ul>
              <div className="card__foot">
                <div className="step__ex"><b>{s.ex.t}</b><span className="muted-txt">{s.ex.d}</span></div>
              </div>
            </Reveal>
          ))}
        </ol>
        <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
          <Button href="/signup" arrow section="home-steps">{cta.primary}</Button>
        </div>
      </div>
    </section>
  );
}
