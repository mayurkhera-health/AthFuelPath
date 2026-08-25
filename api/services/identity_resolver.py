from dataclasses import dataclass
from typing import Optional

import psycopg

from api.database import get_conn


@dataclass
class ResolvedIdentity:
    role: str  # "parent" | "athlete"
    parent_id: Optional[int]
    athlete_id: Optional[int]


class NoExistingAccount(Exception):
    """Verified identity, but no existing AthFuelPath owner matches. Signup
    (creating a new account) is Phase 7 — callers must not create one here."""


class AmbiguousIdentity(Exception):
    """The verified email matches more than one possible owner (e.g. the
    same normalized email exists as both a parent and an athlete login).
    Fail closed — never guess which owner is correct."""


def _row_to_resolved_identity(row: dict) -> ResolvedIdentity:
    return ResolvedIdentity(
        role="parent" if row["parent_id"] is not None else "athlete",
        parent_id=row["parent_id"], athlete_id=row["athlete_id"],
    )


def _resolve_exactly_one_owner(
    email: str, *, email_verified: bool
) -> tuple:
    """
    Read-only. Given an already-normalized email and whether it's verified,
    determines whether it matches exactly one existing parent or athlete
    owner. NEVER writes to auth_identities or any other table -- this is
    the building block resolve_identity() uses internally for its own
    auto-link step, and that a future Apple-specific flow (not part of
    this task) will call directly, BEFORE any write, so its credential
    capture can complete first.

    Returns (role, parent_id, athlete_id) -- role is "parent" or "athlete",
    exactly one of parent_id/athlete_id is set.

    Raises NoExistingAccount if email_verified is False, or email is
    falsy, or there are zero matches.
    Raises AmbiguousIdentity if there are 2+ matches (one parent AND one
    athlete_login both matching the same normalized email).
    """
    if not (email and email_verified):
        raise NoExistingAccount()

    conn = get_conn()
    try:
        parent = conn.execute(
            "SELECT id FROM parents WHERE normalize_email(email) = %s", (email,)
        ).fetchone()
        athlete_login = conn.execute(
            "SELECT athlete_id FROM athlete_logins WHERE normalize_email(email) = %s", (email,)
        ).fetchone()

        matches = []
        if parent:
            matches.append(("parent", dict(parent)["id"], None))
        if athlete_login:
            matches.append(("athlete", None, dict(athlete_login)["athlete_id"]))

        if len(matches) == 0:
            raise NoExistingAccount()
        if len(matches) > 1:
            raise AmbiguousIdentity()

        return matches[0]
    finally:
        conn.close()


def _resolve_exactly_one_parent_owner(email: str) -> int:
    """
    Parent-only variant of _resolve_exactly_one_owner, for flows (Hide-My-
    Email linking) that are explicitly scoped to parent accounts only,
    since only parents have an independent OTP-receiving email channel in
    this architecture. Internally calls _resolve_exactly_one_owner(email,
    email_verified=True) (the caller in this flow has already proven
    ownership via a real OTP, so email_verified is definitionally true at
    this point) and additionally raises NoExistingAccount if the match
    turns out to be an athlete rather than a parent (this flow has no use
    for an athlete match). Returns just parent_id.
    """
    role, parent_id, _athlete_id = _resolve_exactly_one_owner(email, email_verified=True)
    if role != "parent":
        raise NoExistingAccount()
    return parent_id


def resolve_identity(
    *,
    provider: str,
    provider_subject: str,
    email: Optional[str] = None,
    email_verified: bool = False,
) -> ResolvedIdentity:
    """
    Resolve a verified authentication-provider identity to exactly one
    existing AthFuelPath parent or athlete.

    Resolution order:
      1. Exact (provider, provider_subject) match in auth_identities is
         authoritative — return it immediately, never relink based on a
         changed email.
      2. Otherwise, auto-link by email ONLY if email_verified is True and
         email is present, AND the normalized email matches EXACTLY ONE
         existing parent or athlete-login owner. On that single match,
         create the auth_identities row (so step 1 is authoritative next
         time) and return the resolved owner.
      3. No match at all -> raises NoExistingAccount (do not create one).
      4. More than one possible owner -> raises AmbiguousIdentity (fail
         closed; do not create anything, do not guess).

    provider/provider_subject/email are all expected pre-normalized by the
    caller (trim + lowercase for email-shaped values) — this function does
    not re-normalize, to keep the "what got compared" behavior fully
    visible/testable at the call site.
    """
    if not provider or not provider_subject:
        raise ValueError("provider and provider_subject are required")

    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT parent_id, athlete_id FROM auth_identities "
            "WHERE provider = %s AND provider_subject = %s",
            (provider, provider_subject),
        ).fetchone()
        if existing:
            return _row_to_resolved_identity(dict(existing))

        role, parent_id, athlete_id = _resolve_exactly_one_owner(
            email, email_verified=email_verified
        )
        try:
            conn.execute(
                "INSERT INTO auth_identities "
                "(provider, provider_subject, parent_id, athlete_id, email, email_verified) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (provider, provider_subject, parent_id, athlete_id, email, True),
            )
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            # Lost a race against a concurrent identical resolve — the
            # other request's insert already won; re-fetch its result
            # rather than erroring the caller for a benign race.
            existing = conn.execute(
                "SELECT parent_id, athlete_id FROM auth_identities "
                "WHERE provider = %s AND provider_subject = %s",
                (provider, provider_subject),
            ).fetchone()
            if existing:
                return _row_to_resolved_identity(dict(existing))
            raise

        return ResolvedIdentity(role=role, parent_id=parent_id, athlete_id=athlete_id)
    finally:
        conn.close()
