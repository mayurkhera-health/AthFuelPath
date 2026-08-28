import { LegalDoc } from "@/components/Legal";
import { PRIVACY_POLICY, WEBSITE_PRIVACY, WEBSITE_PRIVACY_UPDATED } from "@/content/legal";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Privacy Policy",
  description: "What this website and the waitlist collect, what the app collects, what your athlete is told, and what you control as a parent.",
  path: "/privacy",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

/**
 * The website section renders FIRST, then the app policy.
 *
 * That order is the point. Until 2026-08-28 this page opened on push
 * notifications, meal-confirmation logs and an app nobody can reach, while the
 * only thing a visitor could actually do — hand over their name, their email
 * and, optionally, their child's first name — went unmentioned. A reader now
 * meets the part that applies to them before the part that does not.
 *
 * WEBSITE_PRIVACY is a separate export because PRIVACY_POLICY is copied
 * verbatim from the mobile app and served by its API. See the note in legal.ts.
 */
export default function Privacy() {
  return (
    <LegalDoc
      title="Privacy Policy"
      sections={[...WEBSITE_PRIVACY, ...PRIVACY_POLICY]}
      updated={WEBSITE_PRIVACY_UPDATED}
    />
  );
}
