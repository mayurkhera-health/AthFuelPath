import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Button, TextLink } from "@/components/ui/Button";
import { questionPages, bySlug } from "@/content/questions";
import { cta } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export function generateStaticParams() {
  return questionPages.map((q) => ({ slug: q.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const q = bySlug(slug);
  if (!q) return {};
  /**
   * routeMetadata, like every other route. This used to hand back a bare
   * object with title, description and a canonical, which meant Next fell
   * through to the LAYOUT's openGraph for everything else — so all four
   * question pages advertised the homepage's og:title, the homepage's
   * og:description, and an og:url of the site root. Paste one into Slack and
   * you got a card for the homepage instead of the page you shared.
   *
   * The canonical here was also relative while every other route emits an
   * absolute one. routeMetadata makes both absolute from SITE_URL, which is
   * the same switch the domain cutover flips.
   *
   * The share image stays the default card; these pages have no bespoke one.
   */
  return routeMetadata({
    title: q.title,
    /* Written, not sliced. See the note on `meta` in content/questions.ts. */
    description: q.meta,
    path: `/questions/${q.slug}`,
    imageAlt: "AthFuelPath — fuel smarter, play stronger.",
  });
}

export default async function QuestionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const q = bySlug(slug);
  if (!q) notFound();
  return (
    <>
      <section className="section surface-light">
        <div className="container">
          <div className="prose">
            <span className="eyebrow">Parent question</span>
            <h1 style={{ marginTop: "var(--s4)" }}>{q.h1}</h1>
            <p style={{ fontSize: 18, color: "var(--ink)" }}>{q.intro}</p>
            {q.sections.map((s) => (
              <section key={s.h}>
                <h2>{s.h}</h2>
                <p>{s.p}</p>
                {s.list && <ul>{s.list.map((li) => <li key={li}>{li}</li>)}</ul>}
              </section>
            ))}
            <p className="callout">{q.closing}</p>
            <p><TextLink href="/faq" section="question">{cta.allQuestions}</TextLink></p>
          </div>
        </div>
      </section>
      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">Sort this one for good.</h2>
          <p className="body muted-txt">Set it up once. The app answers it every week, for every session on their schedule.</p>
          <div className="cta-row cta-row--center"><Button href="/signup" hero arrow section="question">{cta.primary}</Button></div>
        </div>
      </section>
    </>
  );
}
