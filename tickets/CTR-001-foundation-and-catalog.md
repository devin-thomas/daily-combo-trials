# CTR-001 - Foundation and catalog validation

## Goal

Create the Python project foundation and a validated structured catalog derived from the supplied Steam and curated game inputs.

## Scope

- Add Python package structure, dependencies, and Vercel entrypoint.
- Normalize the 17 combo-trial game IDs from `fg.js` against `download.json`.
- Add the versioned catalog schema and loader.
- Add catalog validation for games, characters, stable slugs, trial eligibility, and provenance fields.
- Keep raw inputs out of rendered routes.

## Acceptance Criteria

- The application imports with a top-level FastAPI `app`.
- Catalog validation fails clearly for duplicate or invalid stable identifiers.
- Every initial included game has at least one eligible character record.
- Missing description/art fields remain valid and are represented explicitly.
- Tests cover normalization and validation failures.

## Dependencies

None.
