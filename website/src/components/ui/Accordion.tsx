"use client";
import { useId, useState } from "react";
import { Plus } from "./Icons";
import { track, type EventName } from "@/lib/analytics";

export function Accordion({ items, openFirst = true }: { items: { q: string; a: string; event?: EventName }[]; openFirst?: boolean }) {
  const [open, setOpen] = useState<number | null>(openFirst ? 0 : null);
  const base = useId();
  return (
    <div className="acc">
      {items.map((it, i) => {
        const isOpen = open === i;
        const bid = `${base}-b${i}`, pid = `${base}-p${i}`;
        return (
          <div className="acc__item" key={it.q}>
            <h3 style={{ margin: 0 }}>
              <button id={bid} className="acc__btn" aria-expanded={isOpen} aria-controls={pid}
                onClick={() => { const n = isOpen ? null : i; setOpen(n); if (n !== null) { track("faq_open", { question: it.q }); if (it.event) track(it.event); } }}>
                <span>{it.q}</span><Plus />
              </button>
            </h3>
            <div id={pid} role="region" aria-labelledby={bid} className="acc__panel" hidden={!isOpen}>
              <p>{it.a}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
