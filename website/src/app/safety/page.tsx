import { Button, TextLink } from "@/components/ui/Button";
import { cta } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Safety commitments",
  description: "What AthFuelPath shows a soccer player aged 13–17, what it never does, what we collect, and what you control as a parent.",
  path: "/safety",
  image: "/og/safety.jpg",
  imageAlt: "Safe for a growing kid.",
});

const never = [
  { h: "We never put a calorie count in front of your athlete", p: "Not in their day, not on a recipe, not in the weekly report. The day is food and timing: what to eat, and when. They do see a carb and protein target for the day, shown as a fuel gauge, because that is the guidance itself. It reads as fuel to add, and there is no way to fall short of it. The one exception is when your athlete asks the coach what was in a meal they already ate. Then it answers the question they asked, with no target and no judgement attached." },
  { h: "We never track weight or body composition", p: "Weight and BMI are not collected for tracking, never shown back to your athlete, and never scored or trended." },
  { h: "We never treat a window as a failure", p: "An unfilled window reads as coming up, not as something lost. The wording in the app is built to add fuel, not to grade anyone." },
  { h: "We never recommend supplements to a minor", p: "AthFuelPath is food first. Any supplement question goes to a registered dietitian rather than being answered by the app." },
];

const data = [
  { h: "What we collect", p: "Enough to make the guidance fit. Your athlete's age, size, soccer level, season, food preferences and allergies, and their training and game schedule. Nothing beyond that." },
  { h: "Who holds the account", p: "A parent or guardian creates and controls it. An athlete account cannot exist without a verified parent behind it." },
  { h: "What your athlete is told", p: "The app states plainly, in their own account, what their parent can see. Nothing is monitored quietly." },
  { h: "What you control", p: "Meals, photos and the weekly report are each a setting you choose. You can review or delete your family's data whenever you want." },
];

export default function Safety() {
  return (
    <>
      <section className="section surface-dark">
        <div className="container">
          <div className="text-col">
            <span className="eyebrow">Safety &amp; privacy</span>
            <h1 className="h1" style={{ fontSize: "clamp(40px, 6vw, 56px)", marginTop: "var(--s4)" }}>What your athlete never sees.</h1>
            <p className="body muted-txt">Sports nutrition for a 13–17 year old can do real harm if it is handled carelessly. Here are the lines we hold, and what happens to your athlete&apos;s data. Written plainly, so you can check us on it.</p>
          </div>
        </div>
      </section>

      <section className="section surface-light">
        <div className="container">
          <div className="section-head"><h2 className="h2">What we never do.</h2></div>
          <ul className="grid grid-2 grid--tocontent">
            {never.map((n) => (
              <li key={n.h} className="card">
                <h3 className="h4">{n.h}</h3>
                <p className="small muted-txt" style={{ marginTop: "var(--s3)", fontSize: 18 }}>{n.p}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="section surface-tint">
        <div className="container">
          <div className="section-head"><h2 className="h2">Your athlete&apos;s data.</h2></div>
          <ul className="grid grid-2 grid--tocontent">
            {data.map((n) => (
              <li key={n.h} className="card">
                <h3 className="h4">{n.h}</h3>
                <p className="small muted-txt" style={{ marginTop: "var(--s3)", fontSize: 18 }}>{n.p}</p>
              </li>
            ))}
          </ul>
          <p style={{ marginTop: "var(--s6)" }}><TextLink href="/privacy" section="safety-page">Youth data &amp; privacy</TextLink></p>
          {/* site.disclaimer was printed here. It is already in the footer of
              every page, including this one, roughly 300px below — the same
              sentence twice inside one screen. The footer carries it. */}
        </div>
      </section>

      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">Fueling they can follow. Boundaries you can check.</h2>
          <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
            <Button href="/signup" hero arrow section="safety-closing">{cta.primary}</Button>
          </div>
        </div>
      </section>
    </>
  );
}
