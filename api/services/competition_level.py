"""
Canonical competition-level model — single source of truth for validation
(at every write path) and classification (at every read path: event
intensity, hydration/sweat profile). Both derive_intensity() and
derive_sweat_profile() consume classify_competition_level() instead of
keyword-matching the raw stored string independently, so all features
agree on what a given value means.

Root cause this exists to fix: a 2026-07-22 bulk TeamCoach roster-setup
operation overwrote 12 athletes' competition_level with their club's name
("Bay Area Surf") instead of a tier — no code path validated the field, so
a free-text club name silently reached the DB.

MVP stance (no legacy-client compatibility requirement): exactly 3 stored
values are ever valid, at write time AND at read time. There is no
substring/keyword inference ("club" -> competitive_club, "elite" -> elite_club,
etc.) anywhere in this module — an earlier draft had that as a read-time
transition affordance for pre-validation data, and it was removed on
review: keyword inference is exactly the kind of "arbitrary text implies a
tier" logic that must never run, even as a fallback. A stored value that
isn't exactly one of CANONICAL_VALUES is invalid data, full stop — it logs
loudly and gets a safe neutral fallback (never crashes, never guesses),
not a classification.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CANONICAL_VALUES = ("recreational", "competitive_club", "elite_club")


def validate_competition_level(value: str | None) -> str | None:
    """WRITE-TIME gate, used by every create/update model. None (field
    omitted / not provided) is always valid — a partial update that
    doesn't touch this field must stay valid. Any non-None value must be
    exactly one of CANONICAL_VALUES. Raises ValueError, which Pydantic
    field_validator callers turn into a 422 at the API boundary. No
    normalization, no keyword tolerance — a value that isn't already
    exactly correct is rejected, not silently coerced."""
    if value is None:
        return None
    if value not in CANONICAL_VALUES:
        raise ValueError(
            f"competition_level must be one of {CANONICAL_VALUES!r}, got {value!r}. "
            "Free-text values (e.g. a club/team name) are not accepted."
        )
    return value


def classify_competition_level(value: str | None) -> str | None:
    """READ-time lookup for already-stored data. Returns the value itself
    if it's exactly one of CANONICAL_VALUES, otherwise None — never
    raises, never infers a tier from keywords/substrings. An empty/None
    value is a legitimate "no info yet" case (e.g. a brand-new athlete)
    and does not warn; any other non-canonical value logs a warning
    (loud, not silent) and falls back to None so callers apply their own
    neutral default instead of guessing a tier from arbitrary text.
    """
    if not value:
        return None
    if value in CANONICAL_VALUES:
        return value
    logger.warning(
        "competition_level %r is not one of the canonical values %r — treating as "
        "unclassified (safe neutral fallback, not a guessed tier). This athlete's "
        "profile should be corrected to a valid value.",
        value, CANONICAL_VALUES,
    )
    return None
