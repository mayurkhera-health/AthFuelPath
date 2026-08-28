"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { track } from "@/lib/analytics";
import { site, waitlist } from "@/content/site";

/**
 * Waitlist form. Replaced the signup form, which promised an account and a
 * magic link — neither of which the product can deliver yet.
 *
 * Field order is the point of the page: the free-text question comes before the
 * email box. It asks for something before it asks for something.
 *
 * Three accessibility fixes carried over from the pre-launch audit and not to be
 * lost in a future edit:
 *   1. On a validation failure, focus moves to the first invalid field. Without
 *      it a keyboard user submits and nothing appears to happen.
 *   2. Error text carries role="alert" so it is announced, not just rendered.
 *   3. No interactive element is nested inside a <label>. The old consent row
 *      wrapped two links in one, which let a tap on "Terms" toggle the checkbox.
 */
type Errors = Partial<Record<"email" | "parent", string>>;

/** DOM order, so focus lands on the first invalid field a person would reach. */
const FIELD_ORDER = ["email", "parent"] as const;

export function WaitlistForm() {
  const [done, setDone] = useState(false);
  const [answered, setAnswered] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);
  /**
   * Which CTA sent them here, read from ?s= on the URL (see withSource in
   * Button.tsx). Read once on mount from window.location rather than
   * useSearchParams, which would force this page out of static rendering.
   *
   * It is submitted with the form and nowhere else — nothing is recorded about
   * a visitor who does not fill it in, which is what keeps the "no tracking"
   * claim on /privacy true. The API allow-lists the value.
   */
  const source = useRef<string>("unknown");

  useEffect(() => {
    track("waitlist_viewed");
    try { source.current = new URLSearchParams(window.location.search).get("s") || "unknown"; } catch { /* no-op */ }
  }, []);
  useEffect(() => { if (done) doneRef.current?.focus(); }, [done]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const email = String(fd.get("email") ?? "").trim();
    const pain = String(fd.get("pain") ?? "").trim();
    const age = String(fd.get("age") ?? "").trim();
    const club = String(fd.get("club") ?? "").trim();
    const parent = String(fd.get("parent") ?? "").trim();
    const athlete = String(fd.get("athlete") ?? "").trim();
    const oneToOne = fd.get("oneToOne") === "on";

    const errs: Errors = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = "Please enter a valid email.";
    if (!parent) errs.parent = "Please tell us your name.";
    setErrors(errs);
    if (Object.keys(errs).length) {
      const first = FIELD_ORDER.find((f) => errs[f]);
      if (first) form.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }

    setBusy(true);
    setServerErr(null);
    try {
      const r = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, pain, age, club, parent, athlete, oneToOne, source: source.current }),
      });
      if (!r.ok) throw new Error(String(r.status));
      track("waitlist_joined", { answered: pain.length > 0, oneToOne });
      setAnswered(pain.length > 0);
      setDone(true);
    } catch {
      setServerErr(waitlist.error);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="form confirm">
        <span className="confirm__ico"><Tick width={30} height={30} /></span>
        <h1 className="h3" ref={doneRef} tabIndex={-1}>{waitlist.done.h}</h1>
        <p className="body muted-txt">{waitlist.done.p}</p>
        {answered && <p className="small muted-txt">{waitlist.done.pAnswered}</p>}
      </div>
    );
  }

  return (
    <form className="form" onSubmit={onSubmit} noValidate>
      <div>
        <h1 className="h3">{waitlist.h1}</h1>
        <p className="small muted-txt" style={{ marginTop: "var(--s2)" }}>{waitlist.sub}</p>
      </div>

      {/* First, deliberately. See the file header. */}
      <div className="field">
        <label htmlFor="pain">{waitlist.fields.pain.label}</label>
        <textarea id="pain" name="pain" rows={4} maxLength={1200} placeholder={waitlist.fields.pain.placeholder} />
        <span className="hint">{waitlist.fields.pain.hint}</span>
      </div>

      {/* The two required fields, side by side from 720px. */}
      <div className="field-pair">
        <div className={`field${errors.email ? " field--err" : ""}`}>
          <label htmlFor="email">{waitlist.fields.email.label}</label>
          <input
            id="email" name="email" type="email" autoComplete="email" inputMode="email" required
            aria-invalid={!!errors.email} aria-describedby={errors.email ? "e-mail" : "h-mail"}
          />
          {errors.email
            ? <span id="e-mail" className="err" role="alert">{errors.email}</span>
            : <span id="h-mail" className="hint">{waitlist.fields.email.hint}</span>}
        </div>

        <div className={`field${errors.parent ? " field--err" : ""}`}>
          <label htmlFor="parent">{waitlist.fields.parent.label}</label>
          <input
            id="parent" name="parent" maxLength={120} autoComplete="name" required
            aria-invalid={!!errors.parent} aria-describedby={errors.parent ? "e-parent" : "h-parent"}
          />
          {errors.parent
            ? <span id="e-parent" className="err" role="alert">{errors.parent}</span>
            : <span id="h-parent" className="hint">{waitlist.fields.parent.hint}</span>}
        </div>
      </div>

      {/* Paired from 720px. Both are short, both are about the athlete, and
          stacking every field made this column roughly twice the height of the
          panel beside it — about 950px of empty green. One column on a phone. */}
      <div className="field-pair">
        <div className="field">
          <label htmlFor="athlete">{waitlist.fields.athlete.label}</label>
          <input id="athlete" name="athlete" maxLength={80} autoComplete="off" />
          <span className="hint">{waitlist.fields.athlete.hint}</span>
        </div>

        <div className="field">
          <label htmlFor="age">{waitlist.fields.age.label}</label>
          <select id="age" name="age" defaultValue="" aria-describedby="h-age">
            <option value="">Prefer not to say</option>
            {waitlist.fields.age.options.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          {/* The list runs wider than 13–17 on purpose. See the note in
              site.ts — this hint is what keeps that honest. */}
          <span id="h-age" className="hint">{waitlist.fields.age.hint}</span>
        </div>
      </div>

      <div className="field">
        <label htmlFor="club">{waitlist.fields.club.label}</label>
        <input id="club" name="club" maxLength={120} autoComplete="organization" />
        <span className="hint">{waitlist.fields.club.hint}</span>
      </div>

      {/* Checkbox and label are siblings, associated by id. Never wrap a label
          around interactive content — the old consent row did, and a tap on the
          links inside it toggled the box. */}
      <div className="check">
        <input id="oneToOne" name="oneToOne" type="checkbox" />
        <label htmlFor="oneToOne">
          <strong>{waitlist.fields.oneToOne.label}</strong>
          <span className="hint" style={{ display: "block", marginTop: 4 }}>{waitlist.fields.oneToOne.hint}</span>
        </label>
      </div>

      {serverErr && (
        <p className="err" role="alert">
          {serverErr}{" "}
          <a href={`mailto:${site.supportEmail}`} style={{ fontWeight: 700 }}>{site.supportEmail}</a>.
        </p>
      )}

      <Button type="submit" arrow disabled={busy} section="waitlist">
        {busy ? waitlist.sending : waitlist.submit}
      </Button>

      {/* This form had no link to the privacy policy at all, while the coach
          form did — and this is the one that asks for a child's first name.
          /privacy now opens with a section describing exactly these fields. */}
      <p className="form-note">
        {waitlist.privacyNote.a} <Link href={waitlist.privacyNote.href}>{waitlist.privacyNote.link}</Link>.
      </p>
    </form>
  );
}
