import logging

from api.services.email_service import send_email

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, code: str) -> bool:
    """
    Send the OTP code via the existing Gmail SMTP service (api/services/
    email_service.py — already configured and operational in production).
    Returns True on success, False on failure. Callers MUST check this and
    must not report a code as "sent" when delivery actually failed — there
    is no console-log fallback in this path; a failure is a real, reportable
    error, not something to silently swallow.
    """
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#2d6a4f;margin:0 0 8px;">Your AthFuelPath sign-in code</h2>
      <p style="color:#4a6358;margin:0 0 24px;">
        Use this code to sign in. It expires in <strong>10 minutes</strong>.
      </p>
      <div style="background:#f0faf4;border:1.5px solid #b0e8c8;border-radius:12px;
                  padding:24px;text-align:center;margin-bottom:24px;">
        <span style="font-size:36px;font-weight:900;letter-spacing:8px;color:#1b4332;">
          {code}
        </span>
      </div>
      <p style="color:#8aa898;font-size:12px;margin:0;">
        If you didn't request this, you can safely ignore this email.
        AthFuelPath provides educational food guidance — not medical nutrition therapy.
      </p>
    </div>
    """

    ok = send_email(
        subject="Your AthFuelPath sign-in code",
        body=f"Your AthFuelPath sign-in code is {code}. It expires in 10 minutes.",
        to=[to_email],
        html=html,
        from_name="AthFuelPath",
    )
    if not ok:
        logger.error("send_otp_email: Gmail delivery failed for an OTP request")
    return ok
