import { Button, TextLink } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { plan, site, cta } from "@/content/site";

export function Plan({ aside = true, head = true }: { aside?: boolean; head?: boolean } = {}) {
  return (
    <section
      id="pricing"
      className="section surface-light"
      {...(head ? { "aria-labelledby": "pl-h" } : { "aria-label": "Plan and pricing" })}
    >
      <div className="container">
        {head && (
          <div className="section-head section-head--center">
            <span className="eyebrow">{plan.eyebrow}</span>
            <h2 id="pl-h" className="h2 balance">{plan.h2}</h2>
          </div>
        )}
        <div className={aside ? "plan-grid" : "plan-grid plan-grid--solo"}>
          <div className="price-card--dark surface-dark">
            <h3 className="h4">Family plan</h3>
            <p className="price"><b>{site.price}</b><span>{site.priceUnit}</span></p>
            <ul className="feat">
              {plan.features.map((f) => <li key={f}><Tick className="tick" />{f}</li>)}
            </ul>
            <div className="card__foot" style={{ padding: 0 }}>
              <Button href="/signup" arrow section="pricing">{cta.primary}</Button>
              <p className="plan__addon">{plan.addOn}</p>
              <ul className="reassure">
                {plan.reassure.map((r) => <li key={r}><Tick className="tick" width={16} height={16} style={{ color: "var(--lime)" }} />{r}</li>)}
              </ul>
            </div>
          </div>
          {aside && <div className="card">
            <h3 className="h4">{plan.aside.title}</h3>
            {plan.aside.lines.map((l) => <p key={l} className="small muted-txt" style={{ marginTop: "var(--s3)", fontSize: 18 }}>{l}</p>)}
            <div className="card__foot" style={{ display: "grid", gap: "var(--s2)" }}>
              <TextLink href="/faq" section="pricing">{cta.allQuestions}</TextLink>
              <TextLink href="/safety" section="pricing">{cta.safety}</TextLink>
            </div>
          </div>}
        </div>
      </div>
    </section>
  );
}
