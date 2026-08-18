import { Accordion } from "@/components/ui/Accordion";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import { Arrow } from "@/components/ui/Icons";
import { questionPages } from "@/content/questions";
import { faqs, cta, trialLine } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "All questions",
  description: "Setup, safety and billing questions parents ask about AthFuelPath.",
  path: "/faq",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

const groups = ["Setup", "Safety", "Billing"] as const;

export default function FaqPage() {
  const schema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
      <section className="section surface-light">
        <div className="container">
          <div className="text-col">
            <span className="eyebrow">All questions</span>
            <h1 className="h1" style={{ fontSize: "clamp(30px, 5vw, 44px)", marginTop: "var(--s4)" }}>Questions parents ask.</h1>
            {groups.map((g) => (
              <section key={g} style={{ marginTop: "var(--s6)" }}>
                <h2 className="h4" style={{ marginBottom: "var(--s4)" }}>{g}</h2>
                <Accordion items={faqs.filter((f) => f.group === g)} openFirst={g === "Setup"} />
              </section>
            ))}
            <section style={{ marginTop: "var(--s6)" }}>
              <h2 className="h4" style={{ marginBottom: "var(--s4)" }}>Longer reads</h2>
              <ul style={{ display: "grid", gap: "var(--s2)" }}>
                {questionPages.map((q) => (
                  <li key={q.slug}>
                    <Link href={`/questions/${q.slug}`} className="tlink">{q.h1} <Arrow /></Link>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      </section>
      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">Ready when your athlete is.</h2>
          <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
            <Button href="/signup" hero arrow section="faq">{cta.primary}</Button>
          </div>
          <p className="trust-row">{trialLine}</p>
        </div>
      </section>
    </>
  );
}
