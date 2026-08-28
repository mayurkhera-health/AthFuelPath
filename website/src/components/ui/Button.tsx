"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { Arrow } from "./Icons";
import { ctaClick } from "@/lib/analytics";

type Props = {
  href?: string; children: ReactNode;
  variant?: "primary" | "secondary";
  size?: "md" | "sm"; hero?: boolean; arrow?: boolean;
  type?: "button" | "submit"; disabled?: boolean; className?: string;
  /** Section name for the cta_click event. */
  section?: string;
  onClick?: () => void;
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
 */
function withSource(href: string, section?: string): string {
  if (!section || !href.startsWith("/signup") || href.includes("?")) return href;
  return `${href}?s=${encodeURIComponent(section.replace(/-/g, "_"))}`;
}

export function Button({ href, children, variant = "primary", size = "md", hero, arrow, type = "button", disabled, className = "", section, onClick }: Props) {
  const cls = `btn btn--${variant}${size === "sm" ? " btn--sm" : ""}${hero ? " btn--hero" : ""} ${className}`.trim();
  const inner = <>{children}{arrow && <Arrow />}</>;
  const fire = () => { if (section && typeof children === "string") ctaClick(children, section); onClick?.(); };
  if (href) return <Link href={withSource(href, section)} className={cls} onClick={fire}>{inner}</Link>;
  return <button type={type} className={cls} disabled={disabled} onClick={fire}>{inner}</button>;
}

export function TextLink({ href, children, section }: { href: string; children: string; section?: string }) {
  return (
    <Link href={href} className="tlink" onClick={() => section && ctaClick(children, section)}>
      {children} <Arrow />
    </Link>
  );
}
