"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Button } from "./ui/Button";
import { site, cta, coaches } from "@/content/site";

/** <1024 only. Appears after 60% document scroll, hides when the footer CTA is in view. */
export function StickyBar() {
  const [show, setShow] = useState(false);
  /* §20: one CTA label per page. On /coaches the whole page converts on Coach
     Access, so the sticky bar must not offer the parent waitlist beside it. */
  const onCoaches = usePathname() === "/coaches";
  const label = onCoaches ? coaches.ctaLabel : cta.primary;
  const href = onCoaches ? "/coaches#coach-access" : "/signup";
  const strap = onCoaches ? "Early access · opening to clubs" : "Not open yet · Join the waitlist";
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
      <span className="sticky-bar__label">{strap}</span>
      <Button href={href} size="sm" section="sticky-bar">{label}</Button>
    </div>
  );
}
