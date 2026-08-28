import { NextResponse } from "next/server";

/**
 * Signup stub. The website's job is to collect the parent + consent and hand
 * off to the backend (see Account/Billing/Entitlement addendum). When the
 * backend endpoint is live, set SIGNUP_API_URL and this route proxies to it;
 * until then it validates and returns success so the UI flow can be reviewed.
 */
export async function POST(req: Request) {
  const body = await req.json().catch(() => null) as null | { full_name?: string; email?: string; phone?: string; consent_confirmed?: boolean };
  if (!body?.full_name?.trim() || !body.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email) || body.consent_confirmed !== true) {
    return NextResponse.json({ ok: false, error: "invalid" }, { status: 400 });
  }
  const upstream = process.env.SIGNUP_API_URL; // e.g. https://fuelup-youth.fly.dev/api/auth/magic-link/request
  if (upstream) {
    const r = await fetch(upstream, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...body, email: body.email.toLowerCase(), purpose: "signup" }) });
    return NextResponse.json({ ok: r.ok }, { status: r.ok ? 200 : 502 });
  }
  return NextResponse.json({ ok: true, stub: true });
}
