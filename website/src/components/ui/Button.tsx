import Link from "next/link";
import type { ReactNode } from "react";
import { Arrow } from "./Icons";

/**
 * SERVER COMPONENT. Do not add "use client" back without a reason that survives
 * the question below.
 *
 * This was a client component so that every button could fire a `cta_click`
 * analytics event. Two things made that indefensible:
 *
 *   1. The event went nowhere. lib/analytics.ts forwards to window.posthog only
 *      if a PostHog snippet is present, and none is loaded — so the handler ran
 *      on every page of the site and did nothing.
 *   2. It is the wrong mechanism anyway. CTA attribution now rides in the URL
 *      (see withSource below) and lands in a form field the privacy policy
 *      lists. That works without a script, a cookie or a third party, which is
 *      what lets /privacy say the site runs no analytics of any kind.
 *
 * Button is used on every page. Keeping it client-only forced pages with no
 * interactivity at all — /safety, /our-story, /questions/* — to ship a
 * component bundle for a handler that never did anything.
 *
 * If analytics ever comes back, do NOT reopen this file: wrap the specific
 * button that needs measuring in a small client component instead, so one
 * measured CTA does not put every button on the site back into the bundle.
 *
 * The `onClick` prop went with it. Nothing passed one — checked across every
 * call site before removing it.
 */

type Props = {
  href?: string; children: ReactNode;
  variant?: "primary" | "secondary";
  size?: "md" | "sm"; hero?: boolean; arrow?: boolean;
  type?: "button" | "submit"; disabled?: boolean; className?: string;
  /** Which CTA this is. Carried to /signup as ?s= — see withSource. */
  section?: string;
};

/**
 * Any button pointing at /signup carries its own section along as ?s=, so the
 * waitlist entry records which CTA produced it.
 *
 * This is the entire attribution mechanism, and it is deliberately not
 * analytics: no script, no cookie, no third party, and nothing at all recorded
 * about anyone who does not submit the form. The value rides in a URL the
 * person can see and lands in a field the privacy policy lists. It is the only
 * way to answer "did /parents earn its existence?" without falsifying the
 * "no tracking of any kind" claim published on /privacy.
 *
 * Pure, and therefore safe on the server.
 */
function withSource(href: string, section?: string): string {
  if (!section || !href.startsWith("/signup") || href.includes("?")) return href;
  return `${href}?s=${encodeURIComponent(section.replace(/-/g, "_"))}`;
}

export function Button({ href, children, variant = "primary", size = "md", hero, arrow, type = "button", disabled, className = "", section }: Props) {
  const cls = `btn btn--${variant}${size === "sm" ? " btn--sm" : ""}${hero ? " btn--hero" : ""} ${className}`.trim();
  const inner = <>{children}{arrow && <Arrow />}</>;
  if (href) return <Link href={withSource(href, section)} className={cls}>{inner}</Link>;
  return <button type={type} className={cls} disabled={disabled}>{inner}</button>;
}

/** Server component for the same reasons as Button. `section` is kept in the
 *  signature so call sites do not all have to change, and so the intent of
 *  "this link is a measured CTA" survives in the markup. */
export function TextLink({ href, children, section }: { href: string; children: string; section?: string }) {
  return (
    <Link href={withSource(href, section)} className="tlink">
      {children} <Arrow />
    </Link>
  );
}
