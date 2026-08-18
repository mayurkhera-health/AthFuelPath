import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { hero, cta, trialLine } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Our story",
  description: "AthFuelPath started with one family's soccer season. A Registered Dietitian Nutritionist and her own daughter's schedule.",
  path: "/our-story",
  image: "/og/our-story.jpg",
  imageAlt: "Purvi Shah, MS, RDN — the dietitian and soccer mom who built AthFuelPath.",
});

const blocks = [
  { k: "Registered Dietitian Nutritionist", p: ["Purvi Shah has spent her career turning nutrition science into something a family can actually do on a Tuesday night. Long before AthFuelPath, she was the one other parents texted with the same question: what should my kid eat before the game?"] },
  { k: "Soccer mom", p: ["Then her own daughter started playing competitively, and the question became hers. Early sessions. Late kickoffs. Tournament hotels with a mini-fridge and a cooler in the car park. School lunch at eleven, kickoff at six. Long drives home with everyone starving."] },
  { k: "One athlete\u2019s season", p: ["Through club soccer, high-school seasons and the push toward the college game, she did what a dietitian-parent would do. She took her professional training and applied it straight to her daughter\u2019s schedule. Not a plan on paper. A rhythm. What to eat, and when, around whatever was on the calendar that day."] },
  { k: "The gap she kept seeing", p: ["Every family around her wanted the same thing and had no real way to get it. The advice out there was generic, or written for adults, or built on numbers that have no business near a growing teenager. And none of it knew that Tuesday was a session and Saturday was two games."] },
  { k: "Why AthFuelPath exists", p: ["AthFuelPath is that rhythm, made usable for other families. It takes your athlete\u2019s real soccer schedule and turns it into a simple plan for the day. Something the athlete can follow, and the parent can see."] },
  { k: "What we hold to", p: ["Young athletes are not small adults. Training changes what a body needs. Recovery and growth come first. Food comes before supplements. And you should be able to help your kid eat well without a nutrition degree, and without hovering."] },
];

export default function OurStory() {
  return (
    <>
      <section className="section surface-light">
        <div className="container story">
          <div className="story__media">
            <Image
              src="/img/purvi.webp"
              alt="Purvi Shah, founder of AthFuelPath, sitting at an outdoor table"
              width={920}
              height={1150}
              className="photo photo--portrait"
              sizes="(max-width: 900px) 92vw, 420px"
              priority
            />
            <div className="cred" style={{ marginTop: "var(--s5)" }}>
              <Image src="/img/purvi-avatar.webp" alt="" width={192} height={192} className="photo photo--avatar" aria-hidden />
              <span>
                <span className="cred__name">{hero.founder.name}</span><br />
                <span className="cred__role">Registered Dietitian Nutritionist · Soccer mom · Founder</span>
              </span>
            </div>
          </div>
          <div>
            <span className="eyebrow">Our story</span>
            <h1 className="h1" style={{ fontSize: "clamp(36px, 5vw, 52px)", marginTop: "var(--s4)" }}>A dietitian built this for her own daughter.</h1>
            <p className="body" style={{ marginTop: "var(--s4)" }}>AthFuelPath started with one family&apos;s soccer season and one simple question. How does a young player know what to eat, and when?</p>
            <div className="story__blocks" style={{ marginTop: "var(--s6)" }}>
              {blocks.map((b) => (
                <div key={b.k} className="story__block">
                  <span className="eyebrow">{b.k}</span>
                  {b.p.map((t) => <p key={t}>{t}</p>)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
      <section className="surface-dark closing">
        <div className="container">
          <h2 className="h2 balance">It started with one player. Now it's for yours.</h2>
          <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
            <Button href="/signup" hero arrow section="story">{cta.primary}</Button>
          </div>
          <p className="trust-row">{trialLine}</p>
        </div>
      </section>
    </>
  );
}
