import { NextResponse } from "next/server";
import nodemailer from "nodemailer";

/**
 * Waitlist intake.
 *
 * Replaced /api/signup, which returned {"ok":true,"stub":true} — the client
 * showed "check your email" and nothing was ever sent. Nothing here may repeat
 * that mistake: if the entry cannot be delivered, the caller is told so.
 *
 * Delivery reuses the backend's Gmail SMTP credentials (GMAIL_USER /
 * GMAIL_APP_PASSWORD, already Fly secrets on the api app) rather than adding a
 * second email provider. Copy both secrets onto this app to switch it on.
 *
 * A lead must survive an SMTP outage, so the full entry is written to stdout —
 * but ONLY on the failure path, where the log is the last copy in existence.
 * A successful send logs a masked, non-identifying line instead. See the note
 * above the try block.
 */

export const runtime = "nodejs";

const MAX = { pain: 1200, email: 254, club: 140, parent: 120, athlete: 80, role: 40, source: 40 } as const;
/**
 * Which form, on which page, produced this entry. Allow-listed rather than
 * free text: it is written into an email and a log line, so it must not be a
 * channel for arbitrary strings, and a fixed list is what makes the count
 * comparable later. Anything unrecognised becomes "unknown" rather than being
 * rejected — a lead is worth more than a clean label.
 */
const SOURCES = new Set([
  "home_hero", "home_steps", "home_final",   // the three CTAs left on the homepage
  "parents_hero", "parents_final",
  "our_story", "safety_closing", "faq", "question", "sticky_bar",
  "header", "menu",                          // the nav button and the mobile sheet
  "coaches", "unknown",
]);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const AGES = new Set(["Under 13", "13", "14", "15", "16", "17", "18 or older", ""]);

/**
 * Per-machine, per-minute cap. Deliberately modest: this app runs two machines
 * that scale to zero, so the map is per-instance and resets on suspend. It stops
 * a script hammering one box; it is not a substitute for a shared limiter, which
 * belongs in the API once this posts anywhere but an inbox.
 */
const WINDOW_MS = 60_000;
const MAX_PER_WINDOW = 5;
const hits = new Map<string, number[]>();

function rateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= MAX_PER_WINDOW) return true;
  recent.push(now);
  hits.set(ip, recent);
  if (hits.size > 5000) hits.clear(); // crude ceiling; this is a marketing form
  return false;
}

type Entry = {
  kind: "parent" | "coach" | "coach_answer";
  email: string; pain: string; age: string; club: string;
  parent: string; athlete: string; role: string; oneToOne: boolean; source: string;
};

async function deliver(entry: Entry): Promise<boolean> {
  const user = process.env.GMAIL_USER;
  const pass = process.env.GMAIL_APP_PASSWORD;
  const to = (process.env.WAITLIST_TO || user || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!user || !pass || !to.length) {
    console.error("[waitlist] SMTP not configured — entry logged only");
    return false;
  }
  const t = nodemailer.createTransport({
    host: "smtp.gmail.com",
    port: 465,
    secure: true,
    auth: { user, pass },
    connectionTimeout: 8000,
    greetingTimeout: 8000,
    socketTimeout: 8000,
  });
  const dash = (v: string) => v || "—";

  /* Coaches come through /coaches; parents through /signup. Same pipe, same
     rate limit, same log — different letter, because Purvi triages them
     differently and a coach is a club rather than a family. */
  const body = entry.kind === "coach_answer" ? [
    "Hello Purvi,",
    "",
    "A coach who requested access has answered the follow-up question.",
    "",
    `Name:   ${entry.parent}`,
    `Email:  ${entry.email}`,
    "",
    "Biggest fueling challenge they see:",
    entry.pain || "(none)",
    "",
    "—",
    "Sent by the AthFuelPath coaches page. Reply to this email to answer them directly.",
  ].join("\n") : entry.kind === "coach" ? [
    "Hello Purvi,",
    "",
    "A coach has asked for early access to the team view.",
    "Here are the details.",
    "",
    `Name:              ${entry.parent}`,
    `Role:              ${dash(entry.role)}`,
    `Club or program:   ${dash(entry.club)}`,
    `Email:             ${entry.email}`,
    `Came from:         ${entry.source}`,
    "",
    "What they want to see:",
    entry.pain || "(none)",
    "",
    "—",
    "Sent by the AthFuelPath coaches page. Reply to this email to answer them directly.",
  ].join("\n") : [
    "Hello Purvi,",
    "",
    "You have received interest for AthFuelPath.",
    "Here are the details.",
    "",
    `Name of parent:    ${entry.parent}`,
    `Name of athlete:   ${dash(entry.athlete)}`,
    `Parent email:      ${entry.email}`,
    `Age of athlete:    ${dash(entry.age)}`,
    `Club:              ${dash(entry.club)}`,
    `Wants 1:1 review:  ${entry.oneToOne ? "YES" : "no"}`,
    `Came from:         ${entry.source}`,
    "",
    "Comments:",
    entry.pain || "(none)",
    "",
    "—",
    "Sent by the AthFuelPath waitlist form. Reply to this email to answer them directly.",
  ].join("\n");
  await t.sendMail({
    from: `"AthFuelPath waitlist" <${user}>`,
    to,
    // Replying in the mail client answers the parent, not the form.
    replyTo: entry.email,
    /* Prefix first so Purvi can filter: [COACH] is a club, [1:1] is a family
       asking her to look at their week. */
    subject: entry.kind === "coach_answer"
      ? `[COACH · answer] AthFuelPath: ${entry.parent}`
      : entry.kind === "coach"
      ? `[COACH] AthFuelPath: ${entry.parent}${entry.club ? ` · ${entry.club}` : ""}`
      : `${entry.oneToOne ? "[1:1] " : ""}AthFuelPath waitlist: ${entry.parent || entry.email}${entry.club ? ` · ${entry.club}` : ""}`,
    text: body,
  });
  return true;
}

export async function POST(req: Request) {
  const ip = req.headers.get("fly-client-ip") ?? req.headers.get("x-forwarded-for") ?? "unknown";
  if (rateLimited(ip)) {
    return NextResponse.json({ ok: false, error: "rate_limited" }, { status: 429 });
  }

  const body = (await req.json().catch(() => null)) as null | Record<string, unknown>;
  const email = String(body?.email ?? "").trim().slice(0, MAX.email);
  const pain = String(body?.pain ?? "").trim().slice(0, MAX.pain);
  const club = String(body?.club ?? "").trim().slice(0, MAX.club);
  const parent = String(body?.parent ?? "").trim().slice(0, MAX.parent);
  const athlete = String(body?.athlete ?? "").trim().slice(0, MAX.athlete);
  const oneToOne = body?.oneToOne === true;
  const age = String(body?.age ?? "").trim();
  const role = String(body?.role ?? "").trim().slice(0, MAX.role);
  const rawSource = String(body?.source ?? "").trim().slice(0, MAX.source);
  const source = SOURCES.has(rawSource) ? rawSource : "unknown";
  const kind: Entry["kind"] =
    body?.kind === "coach" ? "coach" : body?.kind === "coach_answer" ? "coach_answer" : "parent";

  /**
   * Spam defence, no CAPTCHA.
   *
   * `company` is a honeypot: positioned off-screen, never focusable, invisible
   * to anyone using the form. Anything in it came from a script.
   *
   * `elapsed` is how long the form was open. A person cannot read four labels,
   * type a name, a club and an email in under two seconds.
   *
   * Both return 200 with ok:true. A bot that gets a 400 retries with the field
   * removed; one that gets a success page stops. Nothing is logged or sent.
   */
  const honeypot = String(body?.company ?? "").trim();
  const elapsed = Number(body?.elapsed ?? Number.POSITIVE_INFINITY);
  if (honeypot || (Number.isFinite(elapsed) && elapsed < 2000)) {
    console.log(`[waitlist] discarded (${honeypot ? "honeypot" : `${elapsed}ms`})`);
    return NextResponse.json({ ok: true });
  }

  if (!EMAIL_RE.test(email) || !parent || (kind === "parent" && !AGES.has(age))) {
    return NextResponse.json({ ok: false, error: "invalid" }, { status: 400 });
  }

  const entry: Entry = { kind, email: email.toLowerCase(), pain, age, club, parent, athlete, role, oneToOne, source };

  /**
   * The full entry is written to the log ONLY when delivery fails.
   *
   * It used to be logged on every submission, before the send, so a lead would
   * survive an SMTP outage. That reasoning still holds — losing a parent's
   * answer to a transient mail failure is not acceptable — but it put a child's
   * first name, a parent's name, an email address and free text into the host's
   * logs for every successful signup, where they sit under Fly's retention
   * rather than ours and cannot be pulled back on request.
   *
   * So: a minimal, non-identifying line on success, and the full entry only on
   * the path where it is the last copy in existence. Same guarantee, a fraction
   * of the standing exposure.
   */
  const masked = entry.email.replace(/^(.).*(@.*)$/, "$1***$2");
  try {
    const sent = await deliver(entry);
    if (!sent) {
      console.error(`[waitlist] SMTP not configured — full entry retained: ${JSON.stringify(entry)}`);
      return NextResponse.json({ ok: false, error: "unavailable" }, { status: 503 });
    }
    console.log(`[waitlist] ok kind=${entry.kind} source=${entry.source} ${masked}`);
  } catch (e) {
    console.error(`[waitlist] send failed (${e instanceof Error ? e.message : String(e)}) — full entry retained: ${JSON.stringify(entry)}`);
    return NextResponse.json({ ok: false, error: "unavailable" }, { status: 503 });
  }

  return NextResponse.json({ ok: true });
}
