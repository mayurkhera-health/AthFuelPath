-- Database-level guardrail for athletes.competition_level, alongside the
-- API-level validation added in fix/competition-level-validation
-- (api/services/competition_level.py, wired into AthleteCreate,
-- OnboardingAthlete, and the admin PUT /admin/athletes/{id} route).
--
-- Root cause this defends against a repeat of: a 2026-07-22 bulk
-- TeamCoach roster-setup operation wrote a club name ("Bay Area Surf")
-- into 12 athletes' competition_level, because nothing at any layer
-- validated the field -- including any direct SQL/bulk/admin-console
-- write that bypasses the API entirely, which this constraint is the
-- only defense against.
--
-- NOT VALID: 12 existing rows currently hold 'Bay Area Surf' (confirmed
-- via prior read-only audit). A validated CHECK constraint would fail to
-- add outright with those rows present. NOT VALID adds the constraint
-- immediately -- blocking every NEW insert/update from this point on --
-- without scanning/enforcing it against existing rows. Those 12 rows stay
-- exactly as they are (not touched by this migration) until a human
-- decision corrects them (see the prior session's data-repair-plan
-- report: 3 athletes have provable evidence, 9 need a parent/admin
-- question, tier is never inferred from the club name). Once every row
-- passes, a separate, later migration issues VALIDATE CONSTRAINT
-- (a metadata-only operation once no violating row remains) -- explicitly
-- not run here.

ALTER TABLE athletes
    ADD CONSTRAINT athletes_competition_level_canonical
    CHECK (
        competition_level IS NULL
        OR competition_level IN ('recreational', 'competitive_club', 'elite_club')
    ) NOT VALID;
