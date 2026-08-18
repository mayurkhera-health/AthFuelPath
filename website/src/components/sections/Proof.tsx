import Image from "next/image";
import { proof } from "@/content/site";

/**
 * No invented quotes ever ship. With no real quotes on file this renders the
 * authorship line alone; add entries to `proof.quotes` and the grid appears.
 */
export function Proof() {
  const q = proof.quotes;
  if (!q.length) {
    return (
      <section className="section section--slim surface-light" aria-labelledby="pr-h">
        <div className="container">
          <div className="section-head section-head--center">
            <h2 id="pr-h" className="h2 balance">{proof.h2}</h2>
          </div>
          <p className="affil" style={{ fontSize: 18, maxWidth: "60ch", marginInline: "auto" }}>{proof.affiliation}</p>
        </div>
      </section>
    );
  }
  return (
    <section className="section surface-light" aria-labelledby="pr-h">
      <div className="container">
        <div className="section-head section-head--center">
          <h2 id="pr-h" className="h2 balance">{proof.h2}</h2>
        </div>
        <p className="affil">{proof.affiliation}</p>
        <ul className={`grid${q.length >= 3 ? " grid-3" : ""}`} style={q.length < 3 ? { maxWidth: 560, marginInline: "auto" } : undefined}>
          {q.map((t) => (
            <li key={t.name} className="card">
              <p className="quote">“{t.text}”</p>
              <div className="quote__who card__foot">
                <Image src="/img/purvi-avatar.webp" alt="" width={192} height={192} className="photo photo--round40" aria-hidden />
                <span><b>{t.name}</b><br /><span className="muted-txt">{t.club}</span></span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
