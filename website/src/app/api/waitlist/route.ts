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
 * Every entry is also written to stdout before the send is attempted, so a lead
 * survives in `fly logs` even if SMTP is down or the secrets are missing. Losing
 * a parent's answer to a transient mail failure is not acceptable.
 */

export const runtime = "nodejs";

const MAX = { pain: 1200, email: 254, club: 120, parent: 120, athlete: 80 } as const;
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

type Entry = { email: string; pain: string; age: string; club: string; parent: string; athlete: string; oneToOne: boolean };

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
  const body = [
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
    // "[1:1]" first so Purvi can filter her inbox on it.
    subject: `${entry.oneToOne ? "[1:1] " : ""}AthFuelPath waitlist: ${entry.parent || entry.email}${entry.club ? ` · ${entry.club}` : ""}`,
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

  if (!EMAIL_RE.test(email) || !parent || !AGES.has(age)) {
    return NextResponse.json({ ok: false, error: "invalid" }, { status: 400 });
  }

  const entry: Entry = { email: email.toLowerCase(), pain, age, club, parent, athlete, oneToOne };

  // Written before the send so the lead survives an SMTP failure.
  console.log(`[waitlist] ${JSON.stringify(entry)}`);

  try {
    const sent = await deliver(entry);
    if (!sent) {
      return NextResponse.json({ ok: false, error: "unavailable" }, { status: 503 });
    }
  } catch (e) {
    console.error("[waitlist] send failed:", e instanceof Error ? e.message : String(e));
    return NextResponse.json({ ok: false, error: "unavailable" }, { status: 503 });
  }

  return NextResponse.json({ ok: true });
}
