"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "./ui/Logo";
import { Button } from "./ui/Button";
import { Menu, Close } from "./ui/Icons";
import { nav, cta } from "@/content/site";
import { ctaClick } from "@/lib/analytics";

export function Header() {
  const [open, setOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const path = usePathname();
  /**
   * The nav CTA is "Join the waitlist" on every route, /coaches included.
   *
   * It used to swap to "Request Coach Access" on /coaches. That was reverted:
   * the nav is site navigation, and a button that changes label depending on
   * the page teaches a visitor that the header is unreliable. Coach Access is
   * offered three times inside /coaches — hero, sticky bar, form — which is
   * where a page-specific ask belongs.
   */
  const primary = { label: cta.primary, href: "/signup" };

  useEffect(() => { setOpen(false); }, [path]);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    const el = sheetRef.current;
    const focusables = () => el ? Array.from(el.querySelectorAll<HTMLElement>('a[href],button:not([disabled])')) : [];
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); return; }
      if (e.key !== "Tab") return;
      const f = focusables(); if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      <header className="header">
        <div className="container header__in">
          <Logo />
          <nav className="header__nav" aria-label="Primary">
            {nav.links.map((l) => <Link key={l.href} href={l.href}>{l.label}</Link>)}
          </nav>
          <div className="header__right">
            {nav.login && <Link href={nav.login.href} className="header__login" onClick={() => ctaClick(cta.login, "header")}>{nav.login.label}</Link>}
            <Button href={primary.href} size="sm" section="header">{primary.label}</Button>
            <button className="burger" aria-label="Open menu" aria-expanded={open} aria-controls="menu-sheet" onClick={() => setOpen(true)}>
              <Menu />
            </button>
          </div>
        </div>
      </header>

      {open && (
        <div id="menu-sheet" ref={sheetRef} className="sheet" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="sheet__top">
            <Logo />
            <button className="burger" aria-label="Close menu" onClick={() => setOpen(false)} style={{ marginRight: 0 }}><Close /></button>
          </div>
          <nav className="sheet__links" aria-label="Mobile">
            {nav.links.map((l) => <Link key={l.href} href={l.href}>{l.label}</Link>)}
            <Link href="/faq">All questions</Link>
            {nav.login && <Link href={nav.login.href}>{nav.login.label}</Link>}
          </nav>
          <div className="sheet__foot">
            <Button href={primary.href} arrow section="menu">{primary.label}</Button>
          </div>
        </div>
      )}
    </>
  );
}
