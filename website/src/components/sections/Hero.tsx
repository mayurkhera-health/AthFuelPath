import Image from "next/image";
import { Button } from "@/components/ui/Button";
import { Shot } from "@/components/ui/Shot";
import { hero, cta, trialLine } from "@/content/site";

export function Hero() {
  return (
    <section className="section surface-dark hero" aria-labelledby="hero-h">
      <div className="container hero__grid">
        <div className="hero__copy">
          <span className="eyebrow">{hero.eyebrow}</span>
          <h1 id="hero-h" className="h1">Fuel smarter.<br />Play stronger.</h1>
          <p className="body muted-txt">{hero.sub}</p>
          <div className="cta-row">
            <Button href="/signup" hero arrow section="home-hero">{cta.primary}</Button>
            <Button href="/#how-it-works" variant="secondary" section="hero">{cta.secondary}</Button>
          </div>
          <p className="hero__note">{trialLine}</p>
          <div className="proof-card">
            <Image src="/img/purvi-avatar.webp" alt="" width={192} height={192} className="photo photo--avatar" aria-hidden />
            <p><strong>{hero.founder.name}</strong>. {hero.founder.line}</p>
          </div>
          <ul className="chip-row" aria-label="What AthFuelPath is">
            {hero.chips.map((c) => <li key={c} className="chip">{c}</li>)}
          </ul>
        </div>
        <div className="hero__devices">
          <div className="hero__stack">
          <Shot
            className="device--back"
            src="/screens/schedule.webp"
            w={792}
            h={1180}
            alt="The Schedule screen: rest days, then Tuesday's practice at Twin Creeks with its time and location"
          />
          {/* UNOPTIMIZED, and only this one image on the whole site.
              On athfuelpath-web this file — and only this file — comes back 400
              from /_next/image, while schedule.webp above it and purvi.webp on
              /our-story both return 200. Everything that could explain that has
              been ruled out by measurement rather than argument: the bytes in
              the running container are byte-identical to git (sha256
              64b13f71…), sharp loads and runs there, the raw file serves 200 in
              production, and the same standalone build serves this image 200 at
              384/640/750/828/1080 locally. The cause is still open.

              This is the homepage's LCP element, so it does not get to wait for
              that answer. The source is already a 58KB WebP at 792px and
              `sizes` asks for about 640px, so the optimizer was saving roughly
              24KB on one image — a poor trade against the hero rendering blank.
              Every other image on the site stays optimized.

              Delete this prop the day the root cause is found. */}
          <Shot
            className="device--front"
            src="/screens/today.webp"
            w={792}
            h={1614}
            priority
            unoptimized
            alt="Today's Fuel on a recovery day: the day's protein, carb and hydration needs, then the lunch window with how much of each it calls for and four food ideas"
          />
          </div>
        </div>
      </div>
    </section>
  );
}
