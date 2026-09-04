# CTR-006 - Validation and Vercel readiness

## Goal

Prove the local behavior and document the remaining deployment gate.

## Scope

- Add route, selection, time-zone, persistence, and rendered-copy tests.
- Run the application locally and exercise the main flows.
- Add Vercel configuration and deployment documentation.
- Verify the app requires the Supabase project `elrngwxjmmjfpdedesha` through `DATABASE_URL` for production history.

## Acceptance Criteria

- The documented test command passes.
- The local app starts and serves all required routes.
- UI review covers home, history, game, character, error, and metadata fallback states.
- Vercel entrypoint and dependency metadata are valid.
- Deployment instructions identify the Supabase project, pooled connection, and environment variables without embedding credentials.

## Dependencies

CTR-001 through CTR-005.
