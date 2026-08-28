import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Button, TextLink } from "@/components/ui/Button";
import { questionPages, bySlug } from "@/content/questions";
import { cta } from "@/content/site";

export function generateStaticParams() {
  return questionPages.map((q) => ({ slug: q.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const q = bySlug(slug);
  if (!q) return {};
  return {
    title: q.title,
    description: q.intro.slice(0, 155),
    alternates: { canonical: `/questions/${q.slug}` },
  };
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
