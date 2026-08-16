"""
One-shot test: send a grocery list email with synthetic data.

Run from ~/AthFuelPath:
  GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx python3 scripts/test_grocery_email.py
"""
import os
import sys

# Ensure credentials are present before importing the service.
for var in ("GMAIL_USER", "GMAIL_APP_PASSWORD"):
    if not os.environ.get(var):
        print(f"ERROR: {var} not set. Run as:\n"
              f"  GMAIL_USER=... GMAIL_APP_PASSWORD=... python3 scripts/test_grocery_email.py")
        sys.exit(1)

from api.services.email_templates import grocery_list_email
from api.services.email_service import send_email

TO = "mkhera@zedventures.com"

items = [{
    "athlete_name": "Alex",
    "by_category": {
        "breakfast": ["Greek Yogurt", "Rolled Oats"],
        "pre_fuel":  ["Banana", "Whole Grain Crackers"],
    },
    "extras": ["Almond Butter"],
}]

text, html = grocery_list_email("Priya", "2026-07-13", items)

subject = "Your AthFuelPath grocery list — Jul 13–19  [TEST]"
ok = send_email(subject, text, [TO], html=html)

if ok:
    print(f"Sent to {TO}")
else:
    print("send_email returned False — check GMAIL_USER / GMAIL_APP_PASSWORD")
