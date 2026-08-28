import { Plan } from "@/components/sections/Plan";
import { Button, TextLink } from "@/components/ui/Button";
import { cta, trialLine, site } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Pricing",
  description: `${site.price} per athlete each month, after a ${site.trialDays}-day free trial. Cancel anytime.`,
  path: "/pricing",
  image: "/og/pricing.jpg",
  imageAlt: "One plan. $14.99 per athlete, per month.",
});

export default function Pricing() {
  return (
    <>
      <section className="section surface-dark">
        <div className="container">
          <div className="text-col">
            <span className="eyebrow">Pricing</span>
            <h1 className="h1" style={{ fontSize: "clamp(40px, 6vw, 56px)", marginTop: "var(--s3)" }}>One plan, one price.</h1>
            <p className="body muted-txt">{site.price} per athlete each month, after {site.trialDays} days free. No tiers to compare. Nothing held back for a pricier plan.</p>
            <div className="cta-row"><Button href="/signup" hero arrow section="pricing-hero">{cta.primary}</Button></div>
            <p className="hero__note" style={{ marginTop: "var(--s3)" }}>{trialLine}</p>
          </div>
        </div>
      </section>
      <Plan aside={false} head={false} />
      <section className="section surface-light">
        <div className="container">
          <div className="text-col">
            <h2 className="h2">Questions about the bill?</h2>
            <p className="body muted-txt" style={{ marginTop: "var(--s3)" }}>
              When the trial ends, what happens if you cancel, how to add a second athlete. All answered with the rest.
            </p>
            <p style={{ marginTop: "var(--s4)" }}><TextLink href="/faq" section="pricing-faq">{cta.allQuestions}</TextLink></p>
          </div>
        </div>
      </section>
    </>
  );
}
