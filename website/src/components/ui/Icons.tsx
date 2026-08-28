import type { SVGProps } from "react";
const s = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const Arrow = (p: SVGProps<SVGSVGElement>) => (
  <svg width="18" height="18" viewBox="0 0 24 24" className="arw" aria-hidden {...s} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const Tick = (p: SVGProps<SVGSVGElement>) => (
  <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden {...s} {...p}><path d="M20 6 9 17l-5-5" /></svg>
);
export const Plus = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" aria-hidden className="ico" {...s} {...p}><path d="M12 5v14M5 12h14" /></svg>
);
export const Close = (p: SVGProps<SVGSVGElement>) => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden {...s} {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const Menu = (p: SVGProps<SVGSVGElement>) => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden {...s} {...p}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
);
export const Bolt = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" aria-hidden {...s} {...p}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></svg>
);
export const Mail = (p: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" aria-hidden {...s} {...p}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>
);
