import { WaitlistForm } from "./WaitlistForm";
import { trialLine, waitlist } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Join the waitlist",
  description:
    "AthFuelPath is not open to families yet. Leave your email and tell us what is hardest about feeding your soccer player right now.",
  path: "/signup",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

/**
 * Route kept at /signup on purpose. Every CTA on the site already points here,
 * so switching the content rather than the URL means no redirects to maintain
 * and no dead links while signup is closed. When real signup returns, this file
 * swaps back and nothing else on the site has to change.
 */
export default function SignupPage() {
  return (
    <div className="form-page">
      <aside className="form-page__aside surface-dark">
        <span className="eyebrow">{waitlist.eyebrow}</span>
        <h2 className="h3">Their schedule is already set. We are still building the fueling around it.</h2>
        <ol className="mini-steps">
          <li><span className="n">1</span><span>Tell us what is hardest right now.</span></li>
          <li><span className="n">2</span><span>Purvi reads every answer herself.</span></li>
          <li><span className="n">3</span><span>We email you the day it opens to families.</span></li>
        </ol>
        <p className="notice notice--dark">{trialLine}</p>
      </aside>
      <div className="form-page__main"><WaitlistForm /></div>
    </div>
  );
}
