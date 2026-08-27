-- Finishes the guardrail started in 005_competition_level_check_constraint.sql.
--
-- 005 added athletes_competition_level_canonical NOT VALID: it blocked
-- every new insert/update immediately, but left the 12 then-existing
-- 'Bay Area Surf' rows unvalidated/untouched, since a validated CHECK
-- constraint would have failed to add outright with those rows present.
--
-- Those 12 rows have since been corrected (a separate, reviewed data-repair
-- task -- see the MVP test-athlete competition_level mapping report) to
-- 'competitive_club'. No row in the table now violates the constraint.
--
-- VALIDATE CONSTRAINT is a metadata-only operation once no violating row
-- remains -- it does not rewrite the table, does not touch any row's data,
-- it only flips pg_constraint.convalidated to true so future planner/
-- tooling can treat the constraint as fully enforced history, not just
-- forward-enforced.

ALTER TABLE athletes
    VALIDATE CONSTRAINT athletes_competition_level_canonical;
