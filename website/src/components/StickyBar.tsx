"use client";
import { useEffect, useState } from "react";
import { Button } from "./ui/Button";
import { site, cta } from "@/content/site";

/** <1024 only. Appears after 60% document scroll, hides when the footer CTA is in view. */
export function StickyBar() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const footerCta = document.querySelector(".closing") ?? document.querySelector(".footer");
    let footerVisible = false;
    const io = footerCta
      ? new IntersectionObserver((es) => { footerVisible = es[0].isIntersecting; update(); }, { threshold: 0.05 })
      : null;
    if (footerCta && io) io.observe(footerCta);
    function update() {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const past = max > 0 && window.scrollY / max >= 0.6;
      setShow(past && !footerVisible);
    }
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => { window.removeEventListener("scroll", update); window.removeEventListener("resize", update); io?.disconnect(); };
  }, []);
  return (
    <div className={`sticky-bar${show ? " show" : ""}`} {...(!show ? { inert: true } : {})}>
      <span className="sticky-bar__label">Fueling plan · {site.price}/mo</span>
      <Button href="/signup" size="sm" section="sticky-bar">{cta.primary}</Button>
    </div>
  );
}
