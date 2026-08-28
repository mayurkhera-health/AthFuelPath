import { Button } from "@/components/ui/Button";
import { closing, cta } from "@/content/site";

export function Closing() {
  return (
    <section className="surface-dark closing" aria-labelledby="cl-h">
      <div className="container">
        <h2 id="cl-h" className="h2 balance">{closing.h2}</h2>
        <p className="body muted-txt">{closing.sub}</p>
        <div className="cta-row cta-row--center">
          <Button href="/signup" hero arrow section="home-final">{cta.primary}</Button>
        </div>
        <p className="trust-row">{closing.trust}</p>
      </div>
    </section>
  );
}
