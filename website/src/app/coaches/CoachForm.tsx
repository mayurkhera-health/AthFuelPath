"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Tick } from "@/components/ui/Icons";
import { track } from "@/lib/analytics";
import { site, coaches } from "@/content/site";

/**
 * Coach Access request, in two steps.
 *
 * Step one is four fields and nothing else. The research question that used to
 * sit in the form now runs AFTER the request is recorded, because it is at once
 * the most useful thing on the page and the field most likely to make a coach
 * abandon it. Post-submission it can cost nothing: the lead is already saved.
 *
 * That ordering is the whole design. Do not move the question back above the
 * button to "save a round trip" — the round trip is the point.
 *
 * Posts to /api/waitlist with kind: "coach" rather than taking its own endpoint.
 * That route already has the rate limiting, the stdout log that survives an SMTP
 * failure, and the honest 503; a second endpoint is a second place to get all
 * three wrong. The follow-up answer posts again with the same email so Purvi can
 * match it to the request.
 */
const f = coaches.form;
type Errors = Partial<Record<"name" | "email", string>>;
const FIELD_ORDER = ["name", "email"] as const;
type Stage = "form" | "ask" | "thanks";

export function CoachForm() {
  const [stage, setStage] = useState<Stage>("form");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [role, setRole] = useState<string>(f.role.options[0]);
  const [saved, setSaved] = useState<{ email: string; name: string } | null>(null);
  const headRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => { track("coach_viewed"); }, []);
  useEffect(() => { if (stage !== "form") headRef.current?.focus(); }, [stage]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const name = String(fd.get("name") ?? "").trim();
    const email = String(fd.get("email") ?? "").trim();
    const club = String(fd.get("club") ?? "").trim();

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
        body: JSON.stringify({ kind: "coach", parent: name, email, club, role }),
      });
      if (!r.ok) throw new Error(String(r.status));
      track("coach_requested", { role });
      setSaved({ email, name });
      setStage("ask");
    } catch {
      setServerErr(f.error);
    } finally {
      setBusy(false);
    }
  }

  /** Fire-and-forget: the request is already recorded, so a failure here must
   *  never be shown as if the coach's access request failed. */
  async function sendAnswer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const answer = String(new FormData(e.currentTarget).get("answer") ?? "").trim();
    setStage("thanks");
    if (!answer || !saved) return;
    track("coach_answered");
    fetch("/api/waitlist", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind: "coach_answer", parent: saved.name, email: saved.email, pain: answer }),
    }).catch(() => {});
  }

  if (stage === "ask") {
    return (
      <div className="form coach-form">
        <div className="coach-form__ok">
          <span className="confirm__ico"><Tick width={26} height={26} /></span>
          <div>
            <h3 className="h4" ref={headRef} tabIndex={-1}>{f.done.h}</h3>
            <p className="small muted-txt">{f.done.p}</p>
          </div>
        </div>

        <form onSubmit={sendAnswer} className="coach-form__ask">
          <span className="eyebrow">{f.research.h}</span>
          <label htmlFor="answer" className="coach-form__ask-q">{f.research.p}</label>
          <textarea id="answer" name="answer" rows={3} maxLength={1200} placeholder={f.research.placeholder} />
          <div className="coach-form__ask-row">
            <Button type="submit" arrow section="coaches-research">{f.research.submit}</Button>
            <button type="button" className="tlink" onClick={() => setStage("thanks")}>{f.research.skip}</button>
          </div>
        </form>
      </div>
    );
  }

  if (stage === "thanks") {
    return (
      <div className="form confirm coach-form">
        <span className="confirm__ico"><Tick width={30} height={30} /></span>
        <h3 className="h3" ref={headRef} tabIndex={-1}>{f.done.h}</h3>
        <p className="body muted-txt">{f.done.p}</p>
      </div>
    );
  }

  return (
    <form className="form coach-form" onSubmit={onSubmit} noValidate>
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

      {/* Radios, not a select: four short options visible at once, each its own
          44px target. */}
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

      <div className={`field${errors.email ? " field--err" : ""}`}>
        <label htmlFor="c-email">{f.email.label}</label>
        <input id="c-email" name="email" type="email" inputMode="email" autoComplete="email" required
          aria-invalid={!!errors.email} aria-describedby={errors.email ? "e-cmail" : undefined} />
        {errors.email && <span id="e-cmail" className="err" role="alert">{errors.email}</span>}
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
