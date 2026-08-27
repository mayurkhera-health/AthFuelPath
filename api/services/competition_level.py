"""
Canonical competition-level model — single source of truth for validation
(at every write path) and classification (at every read path: event
intensity, hydration/sweat profile). Everything that used to keyword-match
`competition_level` independently now goes through classify_competition_level()
here instead, so all features agree on what a given value means.

Root cause this exists to fix: a 2026-07-22 bulk TeamCoach roster-setup
operation overwrote 12 athletes' competition_level with their club's name
("Bay Area Surf") instead of a tier — no code path validated the field, so
a free-text club name silently reached the DB and every downstream keyword
match (derive_intensity, derive_sweat_profile) fell through to its
low/unclassified default. Confirmed via git history that derive_intensity's
own keyword logic was unchanged from before these athletes existed — this
was a missing-validation bug, not a code-logic bug.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CANONICAL_VALUES = ("recreational", "competitive_club", "elite_club")


def validate_competition_level(value: str | None) -> str | None:
    """WRITE-TIME gate. None (field omitted / not provided) is always valid —
    a partial update that doesn't touch this field must stay valid. Any
    non-None value must be exactly one of CANONICAL_VALUES — no keyword
    tolerance here; that tolerance is a READ-time transition affordance
    (see classify_competition_level), never a way to get a new bad value
    into the DB. Raises ValueError, which Pydantic field_validator callers
    turn into a 422 at the API boundary."""
    if value is None:
        return None
    if value not in CANONICAL_VALUES:
        raise ValueError(
            f"competition_level must be one of {CANONICAL_VALUES!r}, got {value!r}. "
            "Free-text values (e.g. a club/team name) are not accepted."
        )
    return value


def classify_competition_level(value: str | None) -> str | None:
    """READ-time classification, tolerant of legacy/pre-validation DB values
    during the transition period — this is what derive_intensity() and
    derive_sweat_profile() both call now, so they agree on every value.
    Returns a canonical value or None (never raises — this runs against
    already-stored data, some of which predates the write-time validator
    added alongside this function).

    A non-empty value that classifies via keyword fallback (not an exact
    canonical match) logs a warning — loud, not silent, so drift like the
    "Bay Area Surf" incident surfaces immediately instead of silently
    degrading nutrition guidance for months. An empty/None value is a
    legitimate "no info yet" case (e.g. a brand-new athlete) and does NOT
    warn.
    """
    if not value:
        return None
    if value in CANONICAL_VALUES:
        return value
    level = value.strip().lower()
    if "elite" in level:
        classified = "elite_club"
    elif "recreational" in level:
        classified = "recreational"
    elif "competitive" in level or "club" in level:
        classified = "competitive_club"
    else:
        classified = None
    if classified:
        logger.warning(
            "competition_level %r is not a canonical value — classified as %r via "
            "legacy keyword fallback. This athlete's profile should be corrected.",
            value, classified,
        )
    else:
        logger.warning(
            "competition_level %r is not a canonical value and does not match any "
            "legacy keyword — falling back to unclassified (treated as recreational-"
            "equivalent low intensity / baseline sweat profile). This athlete's "
            "profile should be corrected.",
            value,
        )
    return classified
