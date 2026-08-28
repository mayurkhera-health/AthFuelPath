/** Analytics abstraction (spec §7). Forwards to PostHog when present. */
export type EventName = "cta_click" | "faq_open" | "trial_start" | "signup_started" | "signup_completed" | "waitlist_viewed" | "waitlist_joined" | "question_select"
  | "cook_section_view" | "cook_cta_click" | "recipe_faq_open" | "grocery_faq_open"
  | "ai_coach_section_view" | "ai_coach_example_view" | "ai_coach_signup_click" | "ai_coach_faq_open";
type Props = Record<string, string | number | boolean | undefined>;

declare global {
  interface Window { posthog?: { capture: (e: string, p?: Props) => void } }
}

export function track(event: EventName, props?: Props) {
  if (typeof window === "undefined") return;
  if (window.posthog?.capture) { window.posthog.capture(event, props); return; }
  if (process.env.NODE_ENV !== "production") console.debug("[analytics]", event, props ?? "");
}

/** cta_click always carries label + section. */
export function ctaClick(label: string, section: string) {
  track("cta_click", { label, section });
  /* "Start free trial" is gone in waitlist mode; keep trial_start firing on the
     primary CTA so the funnel stays continuous when signup returns. */
  if (/free trial|waitlist|athlete's plan/i.test(label)) track("trial_start", { section });
}
