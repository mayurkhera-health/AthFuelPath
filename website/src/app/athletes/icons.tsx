import type { SVGProps } from "react";

/**
 * Icons for /athletes only.
 *
 * Local rather than in components/ui/Icons.tsx because nothing else on the site
 * uses them, and that file is the shared set — seven icons every page can reach
 * for. Adding nine one-page icons there would make it a junk drawer.
 *
 * Drawn to the spec: 20px nominal, stroke 2.25, round caps and joins, no fill.
 * They sit inside a coloured badge, so they carry `currentColor` and take their
 * colour from the badge rather than setting one.
 */
const base: SVGProps<SVGSVGElement> = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2.25,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
};

export const Clock = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
);

export const Whistle = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M3 12a5 5 0 0 1 5-5h10l3 3-3 3h-2" /><circle cx="8" cy="12" r="5" /></svg>
);

export const Recover = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M20 12a8 8 0 1 1-2.6-5.9" /><path d="M20 4v4h-4" /></svg>
);

export const Calendar = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></svg>
);

export const Drop = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M12 3s6 6.3 6 10.2A6 6 0 0 1 6 13.2C6 9.3 12 3 12 3Z" /></svg>
);

export const Spark = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z" /></svg>
);

export const Flag = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M5 21V4M5 5h10l-1.5 3L15 11H5" /></svg>
);

export const Plate = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /></svg>
);

export const Check = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6l7-3Z" /><path d="M9 12l2 2 4-4" /></svg>
);
