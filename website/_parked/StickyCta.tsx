"use client";
import { useEffect, useState } from "react";
import { Button } from "./ui/Button";
import { Close } from "./ui/Icons";
import { cta } from "@/content/site";

/** Mobile-only sticky CTA that appears after ~25% scroll and can be dismissed (spec §13, §23). */
export function StickyCta() {
  const [show, setShow] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setShow(max > 0 && window.scrollY / max > 0.25);
    };
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  if (dismissed) return null;
  return (
    <div className={`sticky-cta${show ? " sticky-cta--visible" : ""}`} inert={!show}>
      <Button href="/signup" arrow>{cta.primary}</Button>
      <button className="sticky-cta__close" aria-label="Dismiss" onClick={() => setDismissed(true)}><Close /></button>
    </div>
  );
}
