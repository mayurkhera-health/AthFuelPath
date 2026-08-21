"""
send_otp_email (auth v2.1 Phase 1): the OTP code must never appear in the
email subject line — subjects render on lock screens, in previews, and are
logged by mail gateways. It stays in the body only.
"""

import os
import sys
import types

import pytest


@pytest.fixture
def captured_send(monkeypatch):
    """Stub out the `resend` package so no network call happens, and force
    email.py down its real-send branch (not the dev console-log fallback)
    by setting RESEND_API_KEY."""
    calls = []

    fake_resend = types.SimpleNamespace(
        api_key=None,
        Emails=types.SimpleNamespace(send=lambda payload: calls.append(payload)),
    )
    monkeypatch.setitem(sys.modules, "resend", fake_resend)
    monkeypatch.setenv("RESEND_API_KEY", "test-key-not-real")

    # Re-import fresh so the module-level `import os` picks up the env var
    # at call time (send_otp_email reads os.getenv at call time, not import
    # time, so a plain import is sufficient — no reload needed).
    from api.services import email as email_module
    return email_module, calls


def test_otp_code_never_appears_in_subject(captured_send):
    email_module, calls = captured_send
    email_module.send_otp_email("parent1@example.com", "654321")
    assert len(calls) == 1
    assert "654321" not in calls[0]["subject"]


def test_otp_code_appears_in_body(captured_send):
    email_module, calls = captured_send
    email_module.send_otp_email("parent1@example.com", "654321")
    assert "654321" in calls[0]["html"]


def test_sender_identity_is_athfuelpath_not_fueling2win(captured_send):
    email_module, calls = captured_send
    email_module.send_otp_email("parent1@example.com", "654321")
    assert "Fueling2Win" not in calls[0]["from"]
    assert "Fueling2Win" not in calls[0]["subject"]
    assert "AthFuelPath" in calls[0]["from"]
