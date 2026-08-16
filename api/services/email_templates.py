"""
HTML email templates for AthFuelPath parent/user notifications.

Each public function returns a (plaintext, html) tuple ready to hand to
email_service.send_email(subject, plaintext, [to], html=html).

Rendering uses str.replace() — NOT str.format() — on purpose: the templates
contain CSS blocks full of literal { } braces, which str.format() would choke
on. replace() only swaps the explicit {token} placeholders and leaves CSS alone.
"""

import os
from datetime import datetime, date as _date, timedelta
from html import escape as _escape

# Base URL for links/CTAs. Overridable via env for staging/local.
APP_URL = os.getenv("APP_URL", "https://fuelup-youth.fly.dev").rstrip("/")
# Real, monitored inbox for footer "Contact Support" / reply-to nudges.
SUPPORT_EMAIL = "purvihshah@gmail.com"


def _render(template: str, **values) -> str:
    """Replace {token} placeholders. Safe against literal CSS braces."""
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


# Founder sign-off appended to every email (inside the content block, above the footer).
_SIGNATURE_HTML = (
    '            <div style="margin-top:32px;font-size:16px;color:#4b5563;line-height:1.6;">\n'
    "                Warmly,<br>\n"
    '                <strong style="color:#1f2937;">Purvi Shah, MS, RDN</strong><br>\n'
    "                Founder, AthFuelPath\n"
    "            </div>\n"
)
_SIGNATURE_TEXT = "\n\nWarmly,\nPurvi Shah, MS, RDN\nFounder, AthFuelPath"
# Anchor: the content div's closing tag immediately preceding the footer. Inserting
# the signature before it keeps the sign-off inside the padded content area.
_CONTENT_END = '</div>\n        <div class="footer">'


def _finalize(text: str, html: str):
    """Append the founder signature to both the plaintext and HTML bodies."""
    if _CONTENT_END not in html:  # fail loud in tests if a template's shape drifts
        raise ValueError("signature anchor not found — email template shape changed")
    html = html.replace(_CONTENT_END, _SIGNATURE_HTML + _CONTENT_END, 1)
    return text + _SIGNATURE_TEXT, html


# ---------------------------------------------------------------------------
# Template 1: Welcome (parent signup)
# ---------------------------------------------------------------------------
_WELCOME_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to AthFuelPath</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
        .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 20px; text-align: center; color: white; }
        .logo { font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .content { padding: 40px 30px; }
        .greeting { font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #1f2937; }
        .body-text { font-size: 16px; line-height: 1.5; color: #4b5563; margin-bottom: 14px; }
        .cta-button { display: inline-block; background-color: #10b981; color: white; padding: 14px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 16px; margin-bottom: 20px; }
        .next-step { font-size: 14px; color: #6b7280; background-color: #f3f4f6; padding: 16px; border-radius: 6px; margin-top: 20px; }
        .what-to-expect { background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 14px 18px; border-radius: 4px; margin-bottom: 14px; color: #4b5563; font-size: 15px; }
        .what-to-expect strong { color: #065f46; }
        .what-to-expect ul { margin: 8px 0 0; padding-left: 20px; }
        .what-to-expect li { margin-bottom: 4px; }
        .tagline { font-size: 16px; font-weight: 700; color: #065f46; margin-top: 4px; }
        .footer { background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .footer a { color: #10b981; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">🏃 AthFuelPath</div>
        </div>
        <div class="content">
            <div class="greeting">Welcome to AthFuelPath, {parent_name}!</div>
            <div class="body-text">
                You're in. Welcome to AthFuelPath! <strong>{athlete_name}</strong>'s account is set up, and a dietitian-designed fueling plan is ready to go.
            </div>
            <div class="body-text">
                Here's what that means in practice: every recommendation in this app — pre-game meals, recovery snacks, hydration targets — is built on sports nutrition science, calibrated to {athlete_name}'s sport, training load, and age. This isn't generic diet advice. It's the same caliber of fueling strategy elite athletes rely on, simplified for a teen training schedule.
            </div>
            <div class="what-to-expect">
                <strong>What to expect:</strong>
                <ul>
                    <li>Personalized fueling guidance for training days, game days, and recovery</li>
                    <li>Smart adjustments as training intensity changes through the season</li>
                    <li>Simple, athlete-friendly recommendations {athlete_name} can actually follow</li>
                </ul>
            </div>
            <div class="body-text">
                The app is built for performance, not restriction — helping {athlete_name} train harder, recover faster, and show up strong on game day.
            </div>
            <div class="tagline">Dietitian-designed. Game-day ready.</div>
        </div>
        <div class="footer">
            <p>© 2026 AthFuelPath. Fueling the next generation of athletes.</p>
        </div>
    </div>
</body>
</html>"""


def welcome_email(parent_name: str, athlete_name: str):
    html = _render(_WELCOME_HTML, parent_name=parent_name, athlete_name=athlete_name, app_url=APP_URL)
    text = (
        f"Welcome to AthFuelPath, {parent_name}!\n\n"
        f"You're in. Welcome to AthFuelPath! {athlete_name}'s account is set up, and a "
        "dietitian-designed fueling plan is ready to go.\n\n"
        "Here's what that means in practice: every recommendation in this app — pre-game "
        "meals, recovery snacks, hydration targets — is built on sports nutrition science, "
        f"calibrated to {athlete_name}'s sport, training load, and age. This isn't generic "
        "diet advice. It's the same caliber of fueling strategy elite athletes rely on, "
        "simplified for a teen training schedule.\n\n"
        "What to expect:\n"
        "- Personalized fueling guidance for training days, game days, and recovery\n"
        "- Smart adjustments as training intensity changes through the season\n"
        f"- Simple, athlete-friendly recommendations {athlete_name} can actually follow\n\n"
        "The app is built for performance, not restriction — helping "
        f"{athlete_name} train harder, recover faster, and show up strong on game day.\n\n"
        "Dietitian-designed. Game-day ready."
    )
    return _finalize(text, html)


# ---------------------------------------------------------------------------
# Templates 2 & 3: Acknowledgement emails (problem report / feature idea).
# Both share ONE template — same shell, only the copy differs.
# ---------------------------------------------------------------------------
_ACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.5; color: #333; background-color: #f9fafb; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
        .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 20px; text-align: center; color: white; }
        .header-emoji { font-size: 30px; margin-bottom: 4px; }
        .logo { font-size: 24px; font-weight: bold; }
        .content { padding: 32px 30px; }
        .greeting { font-size: 18px; font-weight: 600; margin-bottom: 12px; color: #1f2937; }
        .body-text { font-size: 16px; line-height: 1.5; color: #4b5563; margin-bottom: 14px; }
        .submitted-box { background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 14px 18px; margin-bottom: 16px; border-radius: 4px; }
        .submitted-box strong { color: #065f46; display: block; margin-bottom: 6px; }
        .submitted-box .quote { color: #4b5563; }
        .steps { margin: 4px 0 16px; }
        .step { display: flex; margin-bottom: 10px; }
        .step-num { flex-shrink: 0; width: 26px; height: 26px; line-height: 26px; text-align: center; border-radius: 50%; background-color: #d1fae5; color: #065f46; font-weight: 600; font-size: 13px; margin-right: 10px; }
        .step-text { flex: 1; font-size: 14px; color: #4b5563; padding-top: 3px; }
        .meta { font-size: 14px; color: #4b5563; margin-bottom: 14px; }
        .meta strong { color: #1f2937; }
        .footer { background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .footer a { color: #10b981; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="header-emoji">{emoji}</div>
            <div class="logo">AthFuelPath</div>
        </div>
        <div class="content">
            <div class="greeting">{greeting}</div>
            <div class="body-text">{intro}</div>
            <div class="submitted-box">
                <strong>{submitted_label}</strong>
                <div class="quote">"{submitted_content}"</div>
            </div>
            <div class="body-text"><strong>What happens next:</strong></div>
            <div class="steps">{steps_html}</div>
            <div class="meta">{meta_html}</div>
        </div>
        <div class="footer">
            <p>© 2026 AthFuelPath. Fueling the next generation of athletes.</p>
        </div>
    </div>
</body>
</html>"""


def _ack_email(*, title, emoji, greeting, intro, submitted_label, submitted_content,
               steps, meta_html, meta_text):
    """Shared acknowledgement email — used for both problem reports and feature ideas.
    `submitted_content` is user-provided free text, so it's HTML-escaped for the HTML body."""
    steps_html = "".join(
        f'<div class="step"><div class="step-num">{i}</div>'
        f'<div class="step-text">{s}</div></div>'
        for i, s in enumerate(steps, 1)
    )
    html = _render(
        _ACK_HTML, title=title, emoji=emoji, greeting=greeting, intro=intro,
        submitted_label=submitted_label, submitted_content=_escape(submitted_content),
        steps_html=steps_html, meta_html=meta_html, app_url=APP_URL,
    )
    step_lines = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    text = (
        f"{greeting}\n\n{intro}\n\n"
        f'{submitted_label}\n"{submitted_content}"\n\n'
        f"What happens next:\n{step_lines}\n\n{meta_text}"
    )
    return _finalize(text, html)


def problem_report_email(athlete_name: str, problem_summary: str, report_id):
    return _ack_email(
        title="Bug Report Received - AthFuelPath",
        emoji="🙏",
        greeting="Thanks for reporting this issue!",
        intro=("We received your bug report and we're grateful you took the time to help "
               "us improve AthFuelPath. Your feedback helps us build a better experience for "
               "every athlete."),
        submitted_label="Here's what you reported:",
        submitted_content=problem_summary,
        steps=[
            "We review it — our team reads your report within 24 hours.",
            "We investigate — we reproduce the issue and figure out what's happening.",
            "We fix it — we prioritize and deploy a fix (timeline varies by severity).",
        ],
        meta_html=(f"<strong>Your report ID:</strong> #{report_id}<br>"
                   "Keep this for reference. Need urgent help? Reply to this email or "
                   'contact <a href="mailto:purvihshah@gmail.com" style="color:#10b981;">'
                   "purvihshah@gmail.com</a>."),
        meta_text=(f"Your report ID: #{report_id}\n"
                   "Need urgent help? Reply to this email or contact purvihshah@gmail.com."),
    )


def feature_idea_email(parent_name: str, feature_idea_summary: str, idea_id, submitted_date: str):
    return _ack_email(
        title="Feature Idea Received - AthFuelPath",
        emoji="💡",
        greeting="We love your idea!",
        intro=("Thank you for submitting a feature idea. At AthFuelPath, we build what parents "
               "and athletes ask for — your feedback directly shapes our roadmap."),
        submitted_label="Your idea:",
        submitted_content=feature_idea_summary,
        steps=[
            "We add it to our feature backlog.",
            "We prioritize based on parent and athlete feedback.",
            "We build and ship the top-requested features.",
        ],
        meta_html=(f"<strong>Your idea ID:</strong> #{idea_id}<br>"
                   f"<strong>Submitted:</strong> {submitted_date}"),
        meta_text=(f"Your idea ID: #{idea_id}\nSubmitted: {submitted_date}"),
    )


# ---------------------------------------------------------------------------
# Template 4: Calendar first-sync confirmation
# Sent once per platform when a parent connects BYGA or PlayMetrics for the
# first time (either via Schedule screen upload or Settings → Calendar Sync).
# ---------------------------------------------------------------------------
_CALENDAR_FIRST_SYNC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calendar Synced - AthFuelPath</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
        .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 20px; text-align: center; color: white; }
        .logo { font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .content { padding: 40px 30px; }
        .greeting { font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #1f2937; }
        .body-text { font-size: 16px; line-height: 1.5; color: #4b5563; margin-bottom: 14px; }
        .sync-box { background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 14px 18px; border-radius: 4px; margin-bottom: 14px; color: #4b5563; font-size: 15px; }
        .sync-box strong { color: #065f46; display: block; margin-bottom: 8px; }
        .sync-box ul { margin: 0; padding-left: 20px; }
        .sync-box li { margin-bottom: 4px; }
        .tagline { font-size: 16px; font-weight: 700; color: #065f46; margin-top: 4px; }
        .footer { background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .footer a { color: #10b981; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">🏃 AthFuelPath</div>
        </div>
        <div class="content">
            <div class="greeting">Hi {parent_name},</div>
            <div class="body-text">
                Great news — <strong>{athlete_name}</strong>'s <strong>{platform_label}</strong> calendar is now connected to AthFuelPath. We ran the first sync and here's what was imported:
            </div>
            <div class="sync-box">
                <strong>First sync summary</strong>
                <ul>
{event_lines_html}
                </ul>
            </div>
            <div class="body-text">
                AthFuelPath will check <strong>{platform_label}</strong> every 6 hours and automatically update {athlete_name}'s schedule whenever new events appear — no action needed on your end.
            </div>
            <div class="body-text">
                Every event now has tailored fueling guidance built in: pre-game meals, hydration targets, and recovery snacks calibrated to {athlete_name}'s training load.
            </div>
            <div class="tagline">Synced. Fueled. Ready.</div>
        </div>
        <div class="footer">
            <p>© 2026 AthFuelPath. Fueling the next generation of athletes.</p>
        </div>
    </div>
</body>
</html>"""


def _fmt_date(date_str: str) -> str:
    """Format 'yyyy-mm-dd' as 'Mon, Jul 14'."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %b %-d")
    except Exception:
        return date_str


def calendar_first_sync_email(
    parent_name: str,
    athlete_name: str,
    platform_label: str,
    counts: dict,
) -> tuple[str, str, str]:
    """Email 1 — sent once when a parent connects a calendar for the first time.

    counts must have keys: inserted, updated, deleted, feed (ints).
    Returns (subject, plaintext, html).
    """
    inserted = counts.get("inserted", 0)
    total = counts.get("feed", inserted)

    lines = []
    if inserted > 0:
        lines.append(f"{inserted} new event{'s' if inserted != 1 else ''} added to {athlete_name}'s schedule")
    if total > inserted:
        lines.append(f"{total} total event{'s' if total != 1 else ''} found in the {platform_label} feed")
    if not lines:
        lines.append(f"Calendar connected — {athlete_name}'s schedule is up to date")

    event_lines_html = "\n".join(f"                    <li>{_escape(l)}</li>" for l in lines)
    html = _render(
        _CALENDAR_FIRST_SYNC_HTML,
        parent_name=_escape(parent_name),
        athlete_name=_escape(athlete_name),
        platform_label=_escape(platform_label),
        event_lines_html=event_lines_html,
    )
    text = (
        f"Hi {parent_name},\n\n"
        f"{athlete_name}'s {platform_label} calendar is now connected to AthFuelPath. "
        f"We ran the first sync and here's what was imported:\n\n"
        + "\n".join(f"- {l}" for l in lines)
        + f"\n\nAthFuelPath will check {platform_label} every 6 hours and automatically update "
        f"{athlete_name}'s schedule whenever new events appear — no action needed on your end.\n\n"
        f"Every event now has tailored fueling guidance built in: pre-game meals, hydration "
        f"targets, and recovery snacks calibrated to {athlete_name}'s training load.\n\n"
        "Synced. Fueled. Ready."
    )
    subject = f"{athlete_name}'s {platform_label} calendar is connected to AthFuelPath"
    text, html = _finalize(text, html)
    return subject, text, html


# ---------------------------------------------------------------------------
# Template 5: Calendar new-events notification
# Sent by the 6-hour sync job whenever it finds NEW events (new UIDs) for an
# athlete. Field updates to existing events do NOT trigger this email.
# ---------------------------------------------------------------------------
_CALENDAR_NEW_EVENTS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Events Synced - AthFuelPath</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
        .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 20px; text-align: center; color: white; }
        .logo { font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .content { padding: 40px 30px; }
        .greeting { font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #1f2937; }
        .body-text { font-size: 16px; line-height: 1.5; color: #4b5563; margin-bottom: 14px; }
        .events-box { background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 14px 18px; border-radius: 4px; margin-bottom: 14px; color: #4b5563; font-size: 15px; }
        .events-box strong { color: #065f46; display: block; margin-bottom: 8px; }
        .events-box ul { margin: 0; padding-left: 20px; }
        .events-box li { margin-bottom: 6px; }
        .event-name { font-weight: 600; color: #1f2937; }
        .event-date { color: #6b7280; font-size: 13px; margin-left: 4px; }
        .note { font-size: 13px; color: #6b7280; background-color: #f3f4f6; padding: 12px 16px; border-radius: 6px; margin-top: 8px; }
        .footer { background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .footer a { color: #10b981; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">🏃 AthFuelPath</div>
        </div>
        <div class="content">
            <div class="greeting">Hi {parent_name},</div>
            <div class="body-text">
                We found <strong>{count} new event{plural}</strong> in <strong>{athlete_name}</strong>'s <strong>{platform_label}</strong> calendar during our latest sync:
            </div>
            <div class="events-box">
                <strong>New events added</strong>
                <ul>
{event_items_html}
                </ul>
            </div>
            <div class="body-text">
                These are now live in AthFuelPath with personalized fueling guidance for each session.
            </div>
            <div class="note">
                AthFuelPath checks {platform_label} every 6 hours to keep {athlete_name}'s schedule current. You'll hear from us whenever something new appears.
            </div>
        </div>
        <div class="footer">
            <p>© 2026 AthFuelPath. Fueling the next generation of athletes.</p>
        </div>
    </div>
</body>
</html>"""


def calendar_new_events_email(
    parent_name: str,
    athlete_name: str,
    platform_label: str,
    new_events: list[dict],
) -> tuple[str, str, str]:
    """Email 2 — sent by the 6-hour sync job when it finds new events (new UIDs).

    new_events: list of dicts with keys event_name, event_date, event_type.
    Returns (subject, plaintext, html).
    """
    count = len(new_events)
    plural = "s" if count != 1 else ""

    items_html = []
    items_text = []
    for ev in new_events:
        name = _escape(ev.get("event_name", "Event"))
        date = _fmt_date(ev.get("event_date", ""))
        items_html.append(
            f'                    <li><span class="event-name">{name}</span>'
            f'<span class="event-date">— {_escape(date)}</span></li>'
        )
        items_text.append(f"- {ev.get('event_name', 'Event')} ({date})")

    event_items_html = "\n".join(items_html)
    html = _render(
        _CALENDAR_NEW_EVENTS_HTML,
        parent_name=_escape(parent_name),
        athlete_name=_escape(athlete_name),
        platform_label=_escape(platform_label),
        count=str(count),
        plural=plural,
        event_items_html=event_items_html,
    )
    text = (
        f"Hi {parent_name},\n\n"
        f"We found {count} new event{plural} in {athlete_name}'s {platform_label} calendar "
        f"during our latest sync:\n\n"
        + "\n".join(items_text)
        + f"\n\nThese are now live in AthFuelPath with personalized fueling guidance for each session.\n\n"
        f"AthFuelPath checks {platform_label} every 6 hours to keep {athlete_name}'s schedule current. "
        f"You'll hear from us whenever something new appears."
    )
    subject = f"{count} new event{plural} added to {athlete_name}'s schedule from {platform_label}"
    text, html = _finalize(text, html)
    return subject, text, html


# ---------------------------------------------------------------------------
# Template 6: Saturday grocery list reminder email
# ---------------------------------------------------------------------------

_GROCERY_CATEGORY_LABELS: dict[str, str] = {
    "breakfast":     "Breakfast",
    "pre_fuel":      "Pre-Game & Practice Fuel",
    "recovery":      "Recovery",
    "hydration":     "Hydration",
    "dinner_staple": "Dinner",
    "produce":       "Produce",
    "protein":       "Protein",
    "carb":          "Carbs & Grains",
    "fat":           "Healthy Fats",
    "spice":         "Pantry Staples",
    "other":         "Other",
}

_GROCERY_CATEGORY_ORDER = [
    "breakfast", "pre_fuel", "recovery", "hydration", "dinner_staple",
    "produce", "protein", "carb", "fat", "spice", "other",
]

_GROCERY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your AthFuelPath Grocery List</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); }
        .header { background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 20px; text-align: center; color: white; }
        .logo { font-size: 24px; font-weight: bold; margin-bottom: 10px; }
        .content { padding: 40px 30px; }
        .greeting { font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #1f2937; }
        .body-text { font-size: 16px; line-height: 1.5; color: #4b5563; margin-bottom: 14px; }
        .athlete-section { margin-bottom: 28px; }
        .athlete-name { font-size: 15px; font-weight: 700; color: #065f46; background-color: #d1fae5; padding: 6px 12px; border-radius: 4px; display: inline-block; margin-bottom: 14px; }
        .category-group { margin-bottom: 14px; }
        .category-label { font-size: 12px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
        .grocery-items { list-style: none; padding: 0; margin: 0; }
        .grocery-items li { font-size: 15px; color: #1f2937; padding: 5px 0; border-bottom: 1px solid #f3f4f6; }
        .grocery-items li:last-child { border-bottom: none; }
        .extras-section { margin-top: 16px; padding-top: 14px; border-top: 1px dashed #d1d5db; }
        .extras-label { font-size: 12px; font-weight: 700; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
        .note { font-size: 13px; color: #6b7280; background-color: #f3f4f6; padding: 12px 16px; border-radius: 6px; margin-top: 24px; }
        .footer { background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }
        .footer a { color: #10b981; text-decoration: none; }
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">🏃 AthFuelPath</div>
        </div>
        <div class="content">
            <div class="greeting">Your grocery list for the week of {week_range}</div>
            <div class="body-text">Here's everything on your AthFuelPath list heading into the week. Screenshot this or grab what you need before Sunday night.</div>
            {athlete_blocks}
            <div class="note">Your grocery list resets Sunday at midnight. This is your copy to keep.</div>
        </div>
        <div class="footer">
            <p>© 2026 AthFuelPath. Fueling the next generation of athletes.</p>
        </div>
    </div>
</body>
</html>"""


def grocery_list_email(
    parent_name: str,
    week_start: str,
    athlete_items: list[dict],
) -> tuple[str, str]:
    """
    athlete_items: list of {
        "athlete_name": str,
        "by_category": {category_key: [item_name, ...]},
        "extras": [item_name, ...],  # source='custom' items
    }
    Returns (plaintext, html).
    """
    start = _date.fromisoformat(week_start)
    end = start + timedelta(days=6)
    week_range = f"{start.strftime('%b %-d')} – {end.strftime('%b %-d')}"

    show_athlete_name = len(athlete_items) > 1
    html_blocks: list[str] = []
    text_sections: list[str] = []

    for ath in athlete_items:
        ath_html = '<div class="athlete-section">'
        ath_text = ""

        if show_athlete_name:
            ath_html += f'\n            <div class="athlete-name">{_escape(ath["athlete_name"])}</div>'
            ath_text += f"{ath['athlete_name']}:\n"

        for cat in _GROCERY_CATEGORY_ORDER:
            items = ath["by_category"].get(cat, [])
            if not items:
                continue
            label = _GROCERY_CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
            ath_html += (
                f'\n            <div class="category-group">'
                f'\n                <div class="category-label">{_escape(label)}</div>'
                f'\n                <ul class="grocery-items">'
            )
            for item in items:
                ath_html += f"\n                    <li>{_escape(item)}</li>"
            ath_html += "\n                </ul>\n            </div>"
            ath_text += f"\n  {label.upper()}\n"
            for item in items:
                ath_text += f"  — {item}\n"

        if ath.get("extras"):
            ath_html += (
                '\n            <div class="extras-section">'
                '\n                <div class="extras-label">Extra items</div>'
                '\n                <ul class="grocery-items">'
            )
            for item in ath["extras"]:
                ath_html += f"\n                    <li>{_escape(item)}</li>"
            ath_html += "\n                </ul>\n            </div>"
            ath_text += "\n  EXTRA ITEMS\n"
            for item in ath["extras"]:
                ath_text += f"  — {item}\n"

        ath_html += "\n        </div>"
        html_blocks.append(ath_html)
        text_sections.append(ath_text)

    athlete_blocks = "\n".join(html_blocks)
    html = _render(_GROCERY_HTML, week_range=_escape(week_range), athlete_blocks=athlete_blocks)

    text = (
        f"Hi {parent_name},\n\n"
        f"Here's your AthFuelPath grocery list for the week of {week_range}.\n\n"
        + "\n".join(text_sections)
        + "\n\nYour grocery list resets Sunday at midnight. This is your copy to keep."
    )
    return _finalize(text, html)
