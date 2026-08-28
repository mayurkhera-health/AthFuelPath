import { routeMetadata } from "@/lib/meta";
import { Hero } from "@/components/sections/Hero";
import { Questions } from "@/components/sections/Questions";
import { Schedule } from "@/components/sections/Schedule";
import { Steps } from "@/components/sections/Steps";
import { Capabilities } from "@/components/sections/Capabilities";
import { Safety } from "@/components/sections/Safety";
import { LegacyHash } from "@/components/LegacyHash";

export const metadata = routeMetadata({
  title: "AthFuelPath — sports nutrition built around your soccer player's schedule",
  description:
    "AthFuelPath turns your player's practices, games and tournaments into personalised fueling guidance — so they know what to eat, when to eat, and why it matters. For soccer players 13–17.",
  path: "/",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
  bareTitle: true,
});

/**
 * The homepage does RECOGNITION.
 *
 * A parent who has never heard of AthFuelPath should be able to understand the
 * problem, the mechanism (schedule → fuel) and that it is safe for a kid, in
 * under a minute. Everything that answers a later objection now lives on
 * /parents.
 *
 * Removed on 2026-08-28 and moved to /parents:
 *   <Cook />       the recipe and grocery block — the largest thing on the page
 *   <Dietitian />  the 1:1 booking section
 * Between them they were close to half the page height, and neither is needed
 * to understand what the product is. <Capabilities /> replaces both with a
 * four-card index and a link.
 *
 * The page stays PARENT-VOICED. Do not rewrite it into audience-neutral product
 * copy to justify the existence of /parents — it will convert worse and read
 * like every other B2C SaaS homepage.
 */
export default function Home() {
  return (
    <>
      <LegacyHash />
      <Hero />
      <Questions />
      <Schedule />
      <Steps />
      <Capabilities />
      <Safety />
      {/* <Closing /> removed on 2026-08-28.
          The homepage now ends on the trust strip, whose two tertiary links
          hand a reader on to /parents and /safety rather than asking a third
          time. That is coherent for a recognition page — someone who has read
          the whole thing and is still deciding is better served by the page
          that answers objections than by another button.
          THE COST, stated plainly so it is a choice and not a surprise: below
          1024px the sticky bar still offers the waitlist at the bottom, but on
          DESKTOP the last waitlist CTA is now mid-page, in the setup section.
          A reader who scrolls to the end has to use the nav. If waitlist
          sign-ups per visitor drop, this is the first thing to put back. */}
    </>
  );
}
