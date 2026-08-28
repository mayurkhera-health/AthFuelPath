import type { Section } from "@/content/legal";
import { LEGAL_EFFECTIVE_DATE, LEGAL_LAST_UPDATED } from "@/content/legal";

export function LegalDoc({ title, sections }: { title: string; sections: Section[] }) {
  return (
    <section className="section surface-light">
      <div className="container">
        <div className="prose">
          <h1>{title}</h1>
          <p className="small">Effective {LEGAL_EFFECTIVE_DATE} · Last updated {LEGAL_LAST_UPDATED}</p>
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
