"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { track } from "@/lib/analytics";
import { site, coaches } from "@/content/site";

/**
 * Coach early-access enquiry. Posts to /api/waitlist with kind: "coach" rather
 * than getting its own endpoint — that route already has the rate limiting,
 * the stdout log that survives an SMTP failure, and the honest 503. A second
 * endpoint would be a second place to get those wrong.
 *
 * Accessibility rules carried from the pre-launch audit: focus moves to the
 * first invalid field, errors carry role="alert", and no interactive element is
 * nested inside a <label>.
 */
const f = coaches.form;
type Errors = Partial<Record<"name" | "email", string>>;
const FIELD_ORDER = ["name", "email"] as const;

export function CoachForm() {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [role, setRole] = useState<string>(f.role.options[0]);
  const doneRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => { track("coach_viewed"); }, []);
  useEffect(() => { if (done) doneRef.current?.focus(); }, [done]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const name = String(fd.get("name") ?? "").trim();
    const email = String(fd.get("email") ?? "").trim();
    const club = String(fd.get("club") ?? "").trim();
    const want = String(fd.get("want") ?? "").trim();

    const errs: Errors = {};
    if (!name) errs.name = "Please tell us your name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Please enter a valid email.";
    setErrors(errs);
    if (Object.keys(errs).length) {
      const first = FIELD_ORDER.find((k) => errs[k]);
      if (first) form.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }

    setBusy(true);
    setServerErr(null);
    try {
      const r = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind: "coach", parent: name, email, club, role, pain: want }),
      });
      if (!r.ok) throw new Error(String(r.status));
      track("coach_requested", { role });
      setDone(true);
    } catch {
      setServerErr(f.error);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="form confirm">
        <span className="confirm__ico"><Tick width={30} height={30} /></span>
        <h3 className="h3">{f.done.h}</h3>
        <p className="body muted-txt" ref={doneRef} tabIndex={-1}>{f.done.p}</p>
      </div>
    );
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <div className={`field${errors.name ? " field--err" : ""}`}>
        <label htmlFor="c-name">{f.name.label}</label>
        <input id="c-name" name="name" autoComplete="name" required
          aria-invalid={!!errors.name} aria-describedby={errors.name ? "e-cname" : undefined} />
        {errors.name && <span id="e-cname" className="err" role="alert">{errors.name}</span>}
      </div>

      <div className="field">
        <label htmlFor="c-club">{f.club.label}</label>
        <input id="c-club" name="club" maxLength={140} autoComplete="organization" />
      </div>

      {/* Radios, not a select: four short options a coach can see at once, and
          each one is its own 44px target. */}
      <fieldset className="field roleset">
        <legend>{f.role.label}</legend>
        <div className="roleset__opts">
          {f.role.options.map((o) => (
            <label key={o} className={`role${role === o ? " is-sel" : ""}`}>
              <input type="radio" name="role" value={o} checked={role === o} onChange={() => setRole(o)} />
              <span>{o}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="field">
        <label htmlFor="c-want">{f.want.label}</label>
        <textarea id="c-want" name="want" rows={3} maxLength={1200} placeholder={f.want.placeholder} />
        <span className="hint">{f.want.hint}</span>
      </div>

      <div className={`field${errors.email ? " field--err" : ""}`}>
        <label htmlFor="c-email">{f.email.label}</label>
        <input id="c-email" name="email" type="email" inputMode="email" autoComplete="email" required
          aria-invalid={!!errors.email} aria-describedby={errors.email ? "e-cmail" : "h-cmail"} />
        {errors.email
          ? <span id="e-cmail" className="err" role="alert">{errors.email}</span>
          : <span id="h-cmail" className="hint">{f.email.hint}</span>}
      </div>

      {serverErr && (
        <p className="err" role="alert">
          {serverErr} <a href={`mailto:${site.supportEmail}`} style={{ fontWeight: 700 }}>{site.supportEmail}</a>.
        </p>
      )}

      <Button type="submit" arrow disabled={busy} section="coaches">
        {busy ? f.sending : f.submit}
      </Button>
    </form>
  );
}
