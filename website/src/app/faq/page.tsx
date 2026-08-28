import { Accordion } from "@/components/ui/Accordion";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import { Arrow } from "@/components/ui/Icons";
import { questionPages } from "@/content/questions";
import { faqs, cta, faqNotice } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "All questions",
  description: "Setup and safety questions parents ask about AthFuelPath, the sports nutrition app for soccer players 13–17.",
  path: "/faq",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

/* Billing was dropped when pricing was hidden. Groups are filtered to those
   that actually have questions, so removing a group's last FAQ can never leave
   an empty heading on the page again. */
const GROUPS = ["Setup", "Safety", "Billing"] as const;

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
            <p className="notice" style={{ marginTop: "var(--s4)" }}>{faqNotice}</p>
            {GROUPS.filter((g) => faqs.some((f) => f.group === g)).map((g) => (
              <section key={g} style={{ marginTop: "var(--s6)" }}>
                <h2 className="h4" style={{ marginBottom: "var(--s4)" }}>{g}</h2>
                <Accordion items={faqs.filter((f) => f.group === g)} openFirst={g === "Setup"} />
                {/* Three safety questions were removed from this group because
                    each restated a card on /safety, two of them near-verbatim.
                    This link replaces them: one pointer to the full account
                    rather than a shortened second copy of it. */}
                {g === "Safety" && (
                  <p style={{ marginTop: "var(--s4)" }}>
                    <Link href="/safety" className="tlink">Everything we never do, and what we collect <Arrow /></Link>
                  </p>
                )}
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
        </div>
      </section>
    </>
  );
}
