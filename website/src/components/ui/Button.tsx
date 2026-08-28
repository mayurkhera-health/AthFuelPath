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

export function Button({ href, children, variant = "primary", size = "md", hero, arrow, type = "button", disabled, className = "", section, onClick }: Props) {
  const cls = `btn btn--${variant}${size === "sm" ? " btn--sm" : ""}${hero ? " btn--hero" : ""} ${className}`.trim();
  const inner = <>{children}{arrow && <Arrow />}</>;
  const fire = () => { if (section && typeof children === "string") ctaClick(children, section); onClick?.(); };
  if (href) return <Link href={href} className={cls} onClick={fire}>{inner}</Link>;
  return <button type={type} className={cls} disabled={disabled} onClick={fire}>{inner}</button>;
}

export function TextLink({ href, children, section }: { href: string; children: string; section?: string }) {
  return (
    <Link href={href} className="tlink" onClick={() => section && ctaClick(children, section)}>
      {children} <Arrow />
    </Link>
  );
}
