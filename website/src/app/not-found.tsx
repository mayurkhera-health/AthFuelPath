import { Button } from "@/components/ui/Button";
export default function NotFound() {
  return (
    <section className="section surface-light">
      <div className="container center" style={{ minHeight: "50vh" }}>
        <h1 className="h2">That page isn&apos;t on the schedule.</h1>
        <p className="body muted-txt" style={{ marginInline: "auto", marginTop: "var(--s4)" }}>Let&apos;s get you back to the fueling path.</p>
        <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
          <Button href="/" section="404">Back home</Button>
        </div>
      </div>
    </section>
  );
}
