"""
send_otp_email (auth v2.1 Phase 1, Gmail follow-up correction): OTP emails
now go through the existing Gmail SMTP service (api/services/email_service.py)
instead of Resend — Resend was never actually configured in production (no
RESEND_API_KEY anywhere), so every OTP silently fell back to a console-log
print that nobody could see in a live deployment. Gmail is the established,
already-configured, already-operational transactional-email path used by 9
other call sites in this codebase.

The OTP code must never appear in the email subject line — subjects render
on lock screens, in previews, and are logged by mail gateways. It stays in
the body only. There is no console-log fallback in production for this
path — a Gmail delivery failure must be reported back to the caller as a
real failure (False), not silently swallowed.
"""

from unittest.mock import patch

from api.services import email as email_module


def test_gmail_send_success():
    with patch.object(email_module, "send_email", return_value=True) as mock_send:
        result = email_module.send_otp_email("parent1@example.com", "654321")

    assert result is True
    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args
    assert kwargs["subject"] == "Your AthFuelPath sign-in code"
    assert kwargs["to"] == ["parent1@example.com"]
    assert "654321" in kwargs["html"]
    assert "654321" in kwargs["body"]


def test_gmail_send_failure_returns_false():
    with patch.object(email_module, "send_email", return_value=False):
        result = email_module.send_otp_email("parent1@example.com", "654321")

    assert result is False


def test_otp_code_never_appears_in_subject():
    with patch.object(email_module, "send_email", return_value=True) as mock_send:
        email_module.send_otp_email("parent1@example.com", "654321")

    _, kwargs = mock_send.call_args
    assert "654321" not in kwargs["subject"]


def test_otp_code_appears_in_body():
    with patch.object(email_module, "send_email", return_value=True) as mock_send:
        email_module.send_otp_email("parent1@example.com", "654321")

    _, kwargs = mock_send.call_args
    assert "654321" in kwargs["html"]
    assert "654321" in kwargs["body"]


def test_athfuelpath_branding_present_no_fueling2win():
    with patch.object(email_module, "send_email", return_value=True) as mock_send:
        email_module.send_otp_email("parent1@example.com", "654321")

    _, kwargs = mock_send.call_args
    assert kwargs["subject"] == "Your AthFuelPath sign-in code"
    assert "AthFuelPath" in kwargs["html"]
    assert "Fueling2Win" not in kwargs["subject"]
    assert "Fueling2Win" not in kwargs["html"]


def test_otp_sender_display_name_is_athfuelpath():
    with patch.object(email_module, "send_email", return_value=True) as mock_send:
        email_module.send_otp_email("parent1@example.com", "654321")

    _, kwargs = mock_send.call_args
    assert kwargs["from_name"] == "AthFuelPath"
