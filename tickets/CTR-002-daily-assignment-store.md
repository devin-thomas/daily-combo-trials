# CTR-002 - Daily assignment store and selection

## Goal

Persist one immutable daily recommendation per Central-time calendar date.

## Scope

- Add the `DailyAssignment` table and repository/service boundary.
- Support local SQLite and Supabase Postgres through `DATABASE_URL`.
- Implement `America/Chicago` date calculation.
- Implement game-first uniform selection.
- Handle unique-date races by rereading the stored winner.

## Acceptance Criteria

- Repeated reads on the same Central date return the same game and character.
- A new Central date can create exactly one new assignment.
- Adding catalog entries does not rewrite existing assignments.
- UTC dates near midnight are mapped to the correct Central date.
- Database failures are surfaced without raw provider details.

## Dependencies

CTR-001.
