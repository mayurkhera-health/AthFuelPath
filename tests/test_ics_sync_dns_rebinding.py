"""DNS-rebinding TOCTOU regression — api/services/ics_sync.py::fetch_ics_text.

Prior architecture: _is_public_host(host) resolves the hostname ONCE via
socket.getaddrinfo() to validate it, then fetch_ics_text hands the ORIGINAL
HOSTNAME (not a pinned IP) to httpx.get(), which performs its OWN,
independent DNS resolution at actual connect time. A hostname that resolves
to a public IP at validation time and to a private/link-local/cloud-metadata
IP by connect time bypasses the guard entirely — the classic SSRF-via-DNS-
rebinding class (the same mechanism used against cloud metadata endpoints in
the wild).

Fixed by resolving once, validating every candidate IP, and connecting
directly to the validated IP (never letting the HTTP client re-resolve the
hostname) — see _resolve_validated_ips() / fetch_ics_text().

No real DNS rebinding and no contact with any internal/cloud address is
performed here — socket.getaddrinfo is mocked to return a different IP on
each call, fully offline and deterministic.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from api.services import ics_sync


def test_validated_ip_is_actually_used_for_the_connection_not_a_fresh_resolution(monkeypatch):
    """The fetch must connect to the SAME IP that passed validation. If the
    implementation instead hands the original hostname to the HTTP client and
    lets it resolve independently, a hostname that flips its DNS answer
    between the validation lookup and the connect-time lookup reaches an
    address the guard was supposed to block — proving the TOCTOU gap."""
    call_log = []

    def fake_getaddrinfo(host, *args, **kwargs):
        call_log.append(host)
        # 1st resolution (whatever the implementation uses to validate) sees
        # a public IP; ANY later, independent resolution of the same hostname
        # sees the cloud metadata address instead.
        if len(call_log) == 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(ics_sync.socket, "getaddrinfo", fake_getaddrinfo)

    reached_internal = {"flag": False}

    class _FakeStreamCtx:
        def __init__(self, resp):
            self._resp = resp

        def __enter__(self):
            return self._resp

        def __exit__(self, *a):
            return False

    class _FakeResp:
        status_code = 200
        headers = {}
        encoding = "utf-8"

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            yield b"REACHED"

    class _FakeClient:
        """Stands in for httpx.Client: .stream()'s url is whatever the real
        code decided to connect to. If that's a plain hostname (not pinned to
        an IP), this simulates httpx's real connect-time behavior — it
        resolves the hostname ITSELF, independent of anything the caller
        already validated. If the url's host is already a literal IP (i.e.
        pinning happened), no further resolution occurs — exactly what
        pinning is supposed to force."""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url, **kwargs):
            host = urlparse(url).hostname
            try:
                ipaddress.ip_address(host)
                resolved_ip = host
            except ValueError:
                infos = ics_sync.socket.getaddrinfo(host, None)
                resolved_ip = infos[0][4][0]
            if resolved_ip == "169.254.169.254":
                reached_internal["flag"] = True
            return _FakeStreamCtx(_FakeResp())

    monkeypatch.setattr(ics_sync.httpx, "Client", lambda **k: _FakeClient())

    ics_sync.fetch_ics_text("https://attacker.example/feed.ics")

    assert not reached_internal["flag"], (
        "SSRF guard validated a public IP but the actual outbound connection "
        "reached 169.254.169.254 — the hostname was independently re-resolved "
        "at connect time instead of the validated IP being used directly "
        "(DNS-rebinding TOCTOU)."
    )
