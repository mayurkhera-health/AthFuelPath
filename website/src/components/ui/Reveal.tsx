"use client";
import { useEffect, useRef, type ReactNode, type ElementType } from "react";

/** Entrance: opacity 0→1 + translateY 12px→0, 320ms ease-out, 60ms stagger. */
export function Reveal({ children, as: Tag = "div", className = "", i, ...rest }: {
  children: ReactNode; as?: ElementType; className?: string; i?: 1 | 2 | 3 | 4 | 5; [k: string]: unknown;
}) {
  const ref = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    document.documentElement.classList.add("js");
    if (!("IntersectionObserver" in window)) { el.classList.add("in"); return; }
    const r = el.getBoundingClientRect();
    if (r.top < window.innerHeight * 0.95 || r.bottom < 0) { el.classList.add("in"); return; }
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting || e.boundingClientRect.bottom < 0) { el.classList.add("in"); io.unobserve(el); }
    }), { rootMargin: "0px 0px -6% 0px", threshold: [0, 0.05] });
    io.observe(el);

    /**
     * Failsafe. Adding `.js` to <html> hides every un-revealed .rv, so if an
     * observer callback is ever missed — a very fast scroll, a restored scroll
     * position, bfcache — the content stays invisible forever with no way back.
     * Losing an entrance animation is nothing; losing a section of the page is
     * not. After 1.5s, show it regardless.
     */
    const failsafe = setTimeout(() => { el.classList.add("in"); io.unobserve(el); }, 1500);
    const onShow = () => el.classList.add("in");
    window.addEventListener("pageshow", onShow);

    return () => { clearTimeout(failsafe); window.removeEventListener("pageshow", onShow); io.disconnect(); };
  }, []);
  return <Tag ref={ref} className={`rv ${className}`.trim()} data-i={i} {...rest}>{children}</Tag>;
}
