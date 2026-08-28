import Link from "next/link";
import { Mail } from "@/components/ui/Icons";
import { site } from "@/content/site";
import { routeMetadata } from "@/lib/meta";

export const metadata = routeMetadata({
  title: "Log in",
  description: "AthFuelPath lives on your phone. Open the app to log in.",
  path: "/login",
  imageAlt: "AthFuelPath — fuel smarter, play stronger.",
});

export default function LoginPage() {
  const ios = process.env.NEXT_PUBLIC_APP_STORE_URL;
  const android = process.env.NEXT_PUBLIC_PLAY_STORE_URL;
  return (
    <section className="section surface-light">
      <div className="container center" style={{ minHeight: "56vh" }}>
        <span className="confirm__ico" style={{ marginInline: "auto" }}><Mail width={30} height={30} /></span>
        <h1 className="h2" style={{ marginTop: "var(--s5)" }}>AthFuelPath lives on your phone.</h1>
        <p className="body muted-txt" style={{ marginInline: "auto", marginTop: "var(--s4)" }}>Open the app to log in. On your phone right now? Tap below and we&apos;ll open it.</p>
        <div className="cta-row cta-row--center" style={{ marginTop: "var(--s6)" }}>
          <a className="btn btn--primary" href="athfuelpath://login">Open the app</a>
          {ios && <a className="btn btn--secondary" href={ios}>App Store</a>}
          {android && <a className="btn btn--secondary" href={android}>Google Play</a>}
        </div>
        <p className="small muted-txt" style={{ marginTop: "var(--s6)" }}>
          Not a member yet? <Link href="/signup" style={{ fontWeight: 700, color: "var(--forest)" }}>Join the waitlist</Link>.
        </p>
        <p className="small muted-txt" style={{ marginTop: "var(--s3)" }}>
          Trouble logging in? <a href={`mailto:${site.supportEmail}`} style={{ fontWeight: 700, color: "var(--forest)" }}>{site.supportEmail}</a>
        </p>
      </div>
    </section>
  );
}
