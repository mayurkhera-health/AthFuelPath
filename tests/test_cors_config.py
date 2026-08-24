"""Regression test: allow_origins=["*"] combined with allow_credentials=True
is a known bad CORS pairing — browsers respond to it by echoing back the
requesting origin instead of a literal "*" whenever credentials are on,
which effectively grants every website credentialed access. No auth
mechanism in this app uses cookies (session Bearer tokens and X-Admin-Key
both travel in explicit headers a browser wouldn't send automatically), so
allow_credentials was never actually needed.
"""
import os
os.environ["DB_PATH"] = ":memory:"

from fastapi.testclient import TestClient
from api.main import app


def test_cors_does_not_allow_credentials_with_wildcard_origin():
    with TestClient(app) as client:
        r = client.options(
            "/api/auth/session",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert r.headers.get("access-control-allow-credentials") != "true"
