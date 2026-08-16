#!/usr/bin/env python3
"""One-off: send a single test push to an Expo token to verify device delivery
end-to-end — independent of the 15-min scheduler AND of NOTIFICATION_DRY_RUN.

It intentionally POSTs directly to Expo rather than going through
notification_service.send_expo_push (which honors NOTIFICATION_DRY_RUN), so it
actually delivers even while the scheduler is staged in dry-run mode.

Usage (from repo root):
    python -m scripts.send_test_push "ExponentPushToken[xxxxxxxx]"

Expo returns {"data":[{"status":"ok","id":"..."}]} on success, or a per-message
error ticket (e.g. {"status":"error","details":{"error":"DeviceNotRegistered"}}).
"""

import sys

import requests

from api.services.notification_service import EXPO_PUSH_URL


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: python -m scripts.send_test_push "ExponentPushToken[...]"')
        raise SystemExit(1)

    token = sys.argv[1]
    message = {
        "to": token,
        "title": "AthFuelPath test ✅",
        "body": "If you see this, push delivery works.",
        "sound": "default",
    }
    resp = requests.post(EXPO_PUSH_URL, json=[message], timeout=10)
    print(f"HTTP {resp.status_code}")
    print(resp.text)


if __name__ == "__main__":
    main()
