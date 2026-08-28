import type { Section } from "@/content/legal";
import { LEGAL_EFFECTIVE_DATE, LEGAL_LAST_UPDATED } from "@/content/legal";

/**
 * `updated` overrides the shared LEGAL_LAST_UPDATED for one document.
 *
 * /privacy needs it: the app policy is synced from the mobile app and still
 * dated July 2, but the website section added on August 28 sits on the same
 * page. A header reading "Last updated July 2" above a section dated August 28
 * is a contradiction a reader can see, and a privacy policy is the last place
 * you can afford to look careless.
 */
export function LegalDoc({ title, sections, updated }: { title: string; sections: Section[]; updated?: string }) {
  return (
    <section className="section surface-light">
      <div className="container">
        <div className="prose">
          <h1>{title}</h1>
          <p className="small">Effective {LEGAL_EFFECTIVE_DATE} · Last updated {updated ?? LEGAL_LAST_UPDATED}</p>
          {sections.map((s, i) => {
            switch (s.type) {
              case "heading": return <h2 key={i}>{s.text}</h2>;
              case "body": return <p key={i}>{s.text}</p>;
              case "warning": return <div key={i} className="callout"><p style={{ color: "var(--ink)" }}>{s.text}</p></div>;
              case "bullets": return <ul key={i}>{s.items.map((it) => <li key={it}>{it}</li>)}</ul>;
              case "divider": return null;
              case "table": return (
                <div key={i} style={{ overflowX: "auto" }}>
                  <table>
                    <thead><tr>{s.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                    <tbody>{s.rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}>{c}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              );
            }
          })}
        </div>
      </div>
    </section>
  );
}
