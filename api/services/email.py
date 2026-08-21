import os


def send_otp_email(to_email: str, code: str) -> None:
    """Send OTP code via Resend. Falls back to console log in dev."""
    api_key = os.getenv("RESEND_API_KEY")
    from_address = os.getenv("RESEND_FROM_ADDRESS", "AthFuelPath <onboarding@resend.dev>")

    if not api_key:
        print(f"\n{'='*40}")
        print(f"  AthFuelPath OTP Code for {to_email}: {code}")
        print(f"{'='*40}\n")
        return

    import resend  # only imported when key is present
    resend.api_key = api_key

    resend.Emails.send({
        "from": from_address,
        "to": [to_email],
        "subject": "Your AthFuelPath sign-in code",
        "html": f"""
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
        """,
    })
