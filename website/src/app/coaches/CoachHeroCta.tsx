"use client";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { coaches } from "@/content/site";
import { ctaClick } from "@/lib/analytics";

/**
 * Hero actions. A coach should be able to convert without scrolling — the
 * previous version made them read the whole page first.
 *
 * Both links are in-page anchors rather than routes, so they work with the
 * browser's own smooth scrolling (html { scroll-behavior: smooth }) and respect
 * prefers-reduced-motion, which a scripted scroll would not.
 */
export function CoachHeroCta() {
  return (
    <div className="coach-hero__cta">
      <Button href="#coach-access" hero arrow section="coaches-hero">{coaches.ctaLabel}</Button>
      <Link
        href="#coach-dashboard"
        className="tlink coach-hero__see"
        onClick={() => ctaClick(coaches.hero.secondary, "coaches-hero")}
      >
        {coaches.hero.secondary} <span aria-hidden>↓</span>
      </Link>
    </div>
  );
}
