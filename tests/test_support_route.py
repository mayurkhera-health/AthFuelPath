"""Integration tests for the problem-report support route."""

import os
os.environ["DB_PATH"] = ":memory:"

import pytest
from fastapi.testclient import TestClient

from db.setup import init_db
from api.services.db_migrations import run_all
from api.database import get_conn
from api.main import app
import api.routes.support as support


@pytest.fixture
def client(monkeypatch):
    keepalive = get_conn()  # keep the shared in-memory DB alive across requests
    init_db()
    run_all()
    # Capture email attempts instead of sending real SMTP.
    sent = []
    monkeypatch.setattr(
        support, "send_email",
        lambda subject, body, to, attachment_path=None, html=None, bcc=None: sent.append(
            {"subject": subject, "body": body, "to": to,
             "attachment_path": attachment_path, "html": html, "bcc": bcc}
        ) or True,
    )
    with TestClient(app) as c:
        c.sent = sent  # expose captured emails to the test
        yield c
    keepalive.close()


def test_report_saved_to_db_and_returns_201(client):
    r = client.post("/api/support/report", data={
        "description": "The schedule screen crashed when I tapped add.",
        "app_version": "1.0.0",
        "platform": "ios 18",
        "role_hint": "athlete",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)

    row = get_conn().execute(
        "SELECT description, app_version, platform, role_hint FROM problem_reports WHERE id = %s",
        (body["id"],),
    ).fetchone()
    assert row is not None
    assert row["description"] == "The schedule screen crashed when I tapped add."
    assert row["app_version"] == "1.0.0"
    assert row["platform"] == "ios 18"
    assert row["role_hint"] == "athlete"


def test_email_attempted_to_both_recipients(client):
    r = client.post("/api/support/report", data={
        "description": "Something went wrong on the today tab.",
        "role_hint": "parent",
    })
    assert r.status_code == 201, r.text
    assert r.json()["email_sent"] is True

    assert len(client.sent) == 1, "send_email should be attempted exactly once"
    assert client.sent[0]["to"] == ["mayurkhera@gmail.com", "purvihshah@gmail.com"]
    # the report description is carried into the email body
    assert "Something went wrong on the today tab." in client.sent[0]["body"]


def test_email_includes_screenshot_when_provided(client):
    r = client.post(
        "/api/support/report",
        data={"description": "bug with a screenshot attached", "role_hint": "athlete"},
        files={"screenshot": ("shot.png", b"\x89PNG\r\n\x1a\nfakebytes", "image/png")},
    )
    assert r.status_code == 201, r.text
    assert len(client.sent) == 1
    # send_email is called with the stored screenshot path as the attachment
    attachment = client.sent[0]["attachment_path"]
    assert attachment is not None
    assert attachment.endswith(".png")
    # and that path matches what was persisted on the report row
    row = get_conn().execute(
        "SELECT screenshot_url FROM problem_reports WHERE id = %s", (r.json()["id"],)
    ).fetchone()
    assert row["screenshot_url"] == attachment


def test_no_attachment_when_no_screenshot(client):
    r = client.post("/api/support/report", data={"description": "no screenshot here"})
    assert r.status_code == 201, r.text
    assert client.sent[0]["attachment_path"] is None


def test_confirmation_uses_account_email_from_parent_id(client):
    # A logged-in report: the client sends parent_id but no typed reporter_email.
    # The confirmation must go to the account holder's email, resolved server-side.
    conn = get_conn()
    conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES (%s, %s, %s, %s)",
        ("Account Holder", "holder@example.com", "2026-07-02T00:00:00", True),
    )
    conn.commit()
    pid = conn.execute(
        "SELECT id FROM parents WHERE email = %s", ("holder@example.com",)
    ).fetchone()["id"]

    r = client.post("/api/support/report", data={
        "description": "crash on save",
        "parent_id": str(pid),
        # deliberately NO reporter_email
    })
    assert r.status_code == 201, r.text
    # two sends: team notification + confirmation to the account holder
    assert len(client.sent) == 2
    confirm = client.sent[1]
    assert confirm["to"] == ["holder@example.com"]
    assert confirm["bcc"] == ["mayurkhera@gmail.com"]
    assert confirm["html"] is not None  # HTML confirmation


def test_unknown_parent_id_falls_back_to_no_confirmation(client):
    # parent_id that doesn't resolve and no reporter_email -> only the team email.
    r = client.post("/api/support/report", data={
        "description": "orphan report",
        "parent_id": "999999",
    })
    assert r.status_code == 201, r.text
    assert len(client.sent) == 1  # team notification only, no confirmation


def test_blank_description_rejected(client):
    # Count first: the in-memory DB uses a process-wide shared cache, so rows
    # from earlier tests may persist — assert on the delta, not an absolute count.
    before = get_conn().execute("SELECT COUNT(*) AS c FROM problem_reports").fetchone()["c"]
    r = client.post("/api/support/report", data={"description": "   "})
    assert r.status_code == 400, r.text
    after = get_conn().execute("SELECT COUNT(*) AS c FROM problem_reports").fetchone()["c"]
    assert after == before, "a rejected (blank) report must not be persisted"
    # no email attempted on rejected submissions
    assert len(client.sent) == 0
