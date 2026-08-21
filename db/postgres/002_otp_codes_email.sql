-- Auth v2.1 Phase 1: rekey otp_codes from parent_id to normalized email.
-- Adds attempts (lockout counter) and consumed_at (audit stamp). parent_id
-- is kept (not dropped) but made nullable, since Phase 2 will need to issue
-- OTPs to emails with no parent account yet — this migration only prepares
-- the schema for that; no such code path exists until Phase 2.

ALTER TABLE otp_codes ADD COLUMN email TEXT;
ALTER TABLE otp_codes ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE otp_codes ADD COLUMN consumed_at TEXT;

UPDATE otp_codes o
SET email = lower(p.email)
FROM parents p
WHERE o.parent_id = p.id AND o.email IS NULL;

-- Orphaned rows (parent_id pointing at a deleted parent) can't be
-- backfilled — they're already-unusable expired/used codes with no
-- product value, so drop them rather than block the NOT NULL below.
DELETE FROM otp_codes WHERE email IS NULL;

ALTER TABLE otp_codes ALTER COLUMN email SET NOT NULL;
ALTER TABLE otp_codes ALTER COLUMN parent_id DROP NOT NULL;

CREATE INDEX idx_otp_email ON otp_codes(email, used, expires_at);
