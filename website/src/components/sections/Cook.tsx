"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { Arrow } from "@/components/ui/Icons";
import { Shot } from "@/components/ui/Shot";
import { cook, cta } from "@/content/site";
import { track, ctaClick } from "@/lib/analytics";

/**
 * "What to cook this week" — fueling moment → recipe choice → grocery list.
 *
 * The two frames are real captures, not a mock: a recipe with its allergen line
 * and Add to Grocery List, and the list that action produced — each item still
 * carrying the recipe it came from. That attribution is the proof, so it is
 * deliberately visible in both.
 *
 * Deliberately absent: ingredient quantities (the product has none) and any
 * claim that recipes come from the week's schedule (not implemented).
 */
export function Cook() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { track("cook_section_view"); io.disconnect(); } }),
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section id="what-to-cook" ref={ref} className="section surface-dark cook" aria-labelledby="cook-h">
      <div className="container">
        <header className="cook__head">
          <span className="eyebrow">{cook.eyebrow}</span>
          <h2 id="cook-h" className="cook__h2">{cook.h2}</h2>
          <p className="cook__h2b">{cook.h2b}</p>
          <p className="cook__body">{cook.body}</p>
        </header>

        <div className="cook__grid">
          {/* Real captures: the recipe a parent picked, and the list it produced */}
          <div className="cook__visual cook__shots">
            <Shot
              src="/screens/recipe.webp"
              w={792}
              h={1600}
              className="cook__shot"
              alt="A recipe in the app: ingredients, an allergen line reading contains dairy, egg, fish, gluten, a swap tip, and Add to Grocery List"
            />
            <Shot
              src="/screens/grocery.webp"
              w={786}
              h={1600}
              className="device--b"
              alt="The grocery list it produced, grouped into produce, protein, carbs and grains, each item labelled with the recipe it came from"
            />
          </div>

          {/* Three proof points */}
          <div className="cook__points">
            <ol>
              {cook.points.map((pt) => (
                <li key={pt.n}>
                  <span className="cook__n" aria-hidden>{pt.n}</span>
                  <h3 className="cook__ph">{pt.h}</h3>
                  <p className="cook__pp">{pt.p}</p>
                  {pt.labels && (
                    <ul className="cook__labels">
                      {pt.labels.map((l) => <li key={l}>{l}</li>)}
                    </ul>
                  )}
                  {pt.safety && <p className="cook__safety">{pt.safety}</p>}
                  {pt.p2 && <p className="cook__pp">{pt.p2}</p>}
                </li>
              ))}
            </ol>

            <p className="cook__athome">
              <strong>{cook.atHome.h}</strong> {cook.atHome.p}
            </p>

          </div>
        </div>

        <div className="cook__closing">
            <h3 className="cook__ch">{cook.closing.h}</h3>
            <p className="cook__pp">{cook.closing.p}</p>
            <ol className="cook__flow" aria-label="How it fits together">
              {cook.closing.flow.map((f, i) => (
                <li key={f}>
                  {f}
                  {i < cook.closing.flow.length - 1 && <span className="cook__flow-arw" aria-hidden>→</span>}
                </li>
              ))}
            </ol>
            <Link
              href="/signup"
              className="tlink cook__cta"
              onClick={() => { ctaClick(cta.primary, "what-to-cook"); track("cook_cta_click", { label: cta.primary, section: "what-to-cook" }); }}
            >
              {cta.primary} <Arrow />
            </Link>
          </div>
      </div>
    </section>
  );
}
