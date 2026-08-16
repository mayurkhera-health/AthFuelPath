# Legal Section in Settings — Design Spec

**Date:** 2026-06-10  
**Status:** Approved

## Overview

Add a "Legal" section to the Settings drawer in AthFuelPath. The section lists five legal documents fetched from the existing `/api/legal` backend and lets users read any document inline within the same drawer.

## Background

The backend already exposes a full legal document API:

- `GET /api/legal` — returns list of documents (slug, title, updated_at)
- `GET /api/legal/{slug}` — returns full document content
- Five documents are seeded: Privacy Policy, Terms of Service, Medical Disclaimer, Youth Athlete Disclaimer, AI Recommendations Disclaimer
- Route is registered at `/api/legal` in `api/main.py`
- Table `legal_documents` exists in SQLite via `db/setup.py`

The frontend Settings screen (`frontend/src/SettingsScreen.jsx`) has no Legal section today.

## Design

### Settings Menu

- A new "Legal" group label is added between the "Account" section and the "About" section.
- On component mount, `GET /api/legal` is fetched to populate the list of documents.
- While loading: a subtle "Loading…" placeholder appears in the Legal section.
- On success: each document is rendered as a tappable row using the same icon/label/chevron pattern as the Account rows (⚖ icon, document title as label, no description needed).
- On error: a "Could not load documents" message replaces the rows (no crash, no alert).

### Document Detail View

- Tapping a row sets the active section to that document's slug and fetches `GET /api/legal/{slug}`.
- The component renders the detail view (same `BackBar` pattern as Athlete Profile / Notifications).
- Content is rendered as plain text in a scrollable styled `<div>` using `whiteSpace: "pre-wrap"` — no Markdown parser required; the content is readable as-is.
- While fetching: a loading spinner is shown.
- On error: an inline error message with a "Retry" button.

### Navigation

- From Legal document list → tap row → document detail view.
- From document detail → tap "‹ Back" → return to Settings root menu.
- This matches the exact navigation pattern used by Athlete Profile and Notifications.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/SettingsScreen.jsx` | Add Legal section to menu, add document detail view, add fetch logic |

No new files, no backend changes, no new dependencies.

## Out of Scope

- Markdown rendering (content is readable as plain text)
- Admin editing of legal documents from the UI
- Pagination or search within documents
- Any backend changes (already complete)
