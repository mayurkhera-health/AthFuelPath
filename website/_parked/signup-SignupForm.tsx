"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { track } from "@/lib/analytics";
import { cta, site } from "@/content/site";

type Errors = Partial<Record<"full_name" | "email" | "consent", string>>;

export function SignupForm() {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  useEffect(() => { track("signup_started"); }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const full_name = String(fd.get("full_name") ?? "").trim();
    const email = String(fd.get("email") ?? "").trim();
    const phone = String(fd.get("phone") ?? "").trim();
    const consent = fd.get("consent") === "on";
    const errs: Errors = {};
    if (!full_name) errs.full_name = "Please enter your name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Please enter a valid email.";
    if (!consent) errs.consent = "Please confirm you are the parent or guardian.";
    setErrors(errs); if (Object.keys(errs).length) return;
    setBusy(true); setServerErr(null);
    try {
      const r = await fetch("/api/signup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ full_name, email, phone: phone || undefined, consent_confirmed: true }) });
      if (!r.ok) throw new Error("bad");
      track("signup_completed"); setDone(true);
    } catch { setServerErr("Something went wrong. Please try again."); }
    finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="form confirm">
        <span className="confirm__ico"><Tick width={30} height={30} /></span>
        <h1 className="h3">Check your email.</h1>
        <p className="body muted-txt">We sent a link to finish setting up. Open it on your phone and you&apos;ll land in the app to add your athlete.</p>
        <p className="small muted-txt">Nothing arrived? Check spam, or email <a href={`mailto:${site.supportEmail}`} style={{ fontWeight: 700, color: "var(--forest)" }}>{site.supportEmail}</a>.</p>
      </div>
    );
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <div>
        <h1 className="h3">Create your parent account</h1>
        <p className="small muted-txt" style={{ marginTop: "var(--s2)" }}>About a minute. You&apos;ll add your athlete in the app.</p>
      </div>
      <div className={`field${errors.full_name ? " field--err" : ""}`}>
        <label htmlFor="full_name">Your name</label>
        <input id="full_name" name="full_name" autoComplete="name" required aria-invalid={!!errors.full_name} aria-describedby={errors.full_name ? "e-name" : undefined} />
        {errors.full_name && <span id="e-name" className="err">{errors.full_name}</span>}
      </div>
      <div className={`field${errors.email ? " field--err" : ""}`}>
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="email" inputMode="email" required aria-invalid={!!errors.email} aria-describedby={errors.email ? "e-mail" : undefined} />
        {errors.email && <span id="e-mail" className="err">{errors.email}</span>}
      </div>
      <div className="field">
        <label htmlFor="phone">Mobile phone <span className="muted-txt" style={{ fontWeight: 400 }}>(optional)</span></label>
        <input id="phone" name="phone" type="tel" autoComplete="tel" inputMode="tel" placeholder="(555) 555-5555" />
        <span className="hint">Only used for account and schedule notifications you turn on.</span>
      </div>
      <label className="check">
        <input type="checkbox" name="consent" aria-invalid={!!errors.consent} />
        <span>I am the parent or legal guardian of the athlete, and I agree to the <Link href="/terms" style={{ fontWeight: 700, color: "var(--forest)" }}>Terms</Link> and <Link href="/privacy" style={{ fontWeight: 700, color: "var(--forest)" }}>Privacy Policy</Link>. AthFuelPath provides educational sports-nutrition guidance — not medical nutrition therapy.</span>
      </label>
      {errors.consent && <span className="err">{errors.consent}</span>}
      {serverErr && <p className="err" role="alert">{serverErr}</p>}
      <Button type="submit" arrow disabled={busy} section="signup">{busy ? "Creating…" : cta.primary}</Button>
      <p className="small muted-txt">Already have an account? <Link href="/login" style={{ fontWeight: 700, color: "var(--forest)" }}>Log in</Link></p>
    </form>
  );
}
