"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Button } from "./ui/Button";
import { site, cta, coaches } from "@/content/site";

/**
 * <1024 only. Hides when the footer CTA is in view, and can be dismissed.
 *
 * On /coaches it appears once the coach has scrolled PAST the dashboard — the
 * moment they know what they would be asking for. Everywhere else it falls back
 * to 60% scroll depth, because no single section there means the same thing.
 */
export function StickyBar() {
  const [show, setShow] = useState(false);
  /* Dismissible. A bar you cannot close is an advert; one you can is an offer.
     Kept in memory rather than storage: it stays gone for this visit and comes
     back on the next one. */
  const [dismissed, setDismissed] = useState(false);
  const path = usePathname();
  /* The nav CTA is now the same on every route. This bar is page content rather
     than navigation, so it still matches the page: sending a coach to the
     parent waitlist would be the wrong form. */
  const onCoaches = path === "/coaches";
  const label = onCoaches ? coaches.ctaLabel : cta.primary;
  const href = onCoaches ? "#coach-access" : "/signup";
  const strap = onCoaches ? "Early access · opening to clubs" : "Not open yet · Join the waitlist";

  useEffect(() => { setDismissed(false); setShow(false); }, [path]);

  useEffect(() => {
    const trigger = onCoaches ? document.querySelector("#coach-dashboard") : null;
    const footerCta = document.querySelector(".closing") ?? document.querySelector(".footer");
    let footerVisible = false;
    let passed = false;
    const ios: IntersectionObserver[] = [];

    function update() {
      if (trigger) {
        /* Measured on scroll rather than watched with an IntersectionObserver.
           An observer only fires when the intersection ratio CROSSES a
           threshold, so a jump straight past the section — an anchor link, a
           restored scroll position, a deep link — can go from "below the
           viewport, not intersecting" to "above it, not intersecting" without
           ever firing, and the bar would never appear. */
        if (trigger.getBoundingClientRect().bottom < 0) passed = true;
        setShow(passed && !footerVisible);
        return;
      }
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setShow(max > 0 && window.scrollY / max >= 0.6 && !footerVisible);
    }

    if (footerCta) {
      const io = new IntersectionObserver((es) => { footerVisible = es[0].isIntersecting; update(); }, { threshold: 0.05 });
      io.observe(footerCta); ios.push(io);
    }

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      ios.forEach((io) => io.disconnect());
    };
  }, [onCoaches, path]);

  const visible = show && !dismissed;
  return (
    <div className={`sticky-bar${visible ? " show" : ""}`} {...(!visible ? { inert: true } : {})}>
      <span className="sticky-bar__label">{strap}</span>
      <Button href={href} size="sm" section="sticky-bar">{label}</Button>
      <button type="button" className="sticky-bar__x" onClick={() => setDismissed(true)} aria-label="Dismiss">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  );
}
