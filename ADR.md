# Architecture Decision Record

## ADR-001 - Target FastAPI on Vercel

**Status:** Accepted

**Decision:** The experiment targets a FastAPI application deployed to Vercel and keeps the application layer in Python with server-rendered pages.

**Rationale:** The user wants to learn FastAPI through a small personal FGC utility and selected Vercel as the deployment target.

**Consequences:** The first design should avoid requiring a long-running process or a writable local filesystem. Runtime persistence, if needed, must be decided explicitly rather than assumed.

## ADR-002 - Use the curated combo-trial list as the initial game boundary

**Status:** Accepted

**Decision:** The initial challenge catalog starts from `comboTrialGameAppIds` in `fg.js`, rather than trying to infer fighting games or combo-trial support from the full Steam export.

**Rationale:** The user has already performed the domain-specific filtering and supplied the narrower list as the intended source for games with combo trials.

**Consequences:** The catalog still needs verified character rosters and trial coverage. A game may be excluded from the final eligible set if its character/trial metadata cannot be supported honestly.

## ADR-003 - Central time defines the daily boundary

**Status:** Accepted

**Decision:** Daily challenge rollover is based on the Central-time calendar date, with daylight-saving behavior represented by the `America/Chicago` time zone rather than a fixed UTC offset.

**Rationale:** The user specified midnight Central time, and an IANA time zone avoids a seasonal one-hour drift.

**Consequences:** The daily-selection logic must be tested around midnight and daylight-saving transitions. The exact relationship between the daily assignment and manual randomization remains open.

## ADR-004 - Manual randomization does not replace the daily challenge

**Status:** Accepted

**Decision:** The home-page randomize action creates a temporary alternate challenge for the visitor while preserving the current daily challenge.

**Rationale:** The daily prompt should remain stable and meaningful, while the user still needs a way to explore another character or game when desired.

**Consequences:** The interface needs a clear distinction between today's challenge and a temporary alternate. The persistence of the alternate across refreshes is still an implementation detail to settle.

## ADR-005 - Balance selection game-first

**Status:** Accepted

**Decision:** Select the trial game uniformly from the eligible game list, then select the character uniformly from that game's eligible roster.

**Rationale:** This matches the requested random game followed by random character behavior and prevents games with larger rosters from dominating the daily rotation.

**Consequences:** The catalog must expose a stable roster for each eligible game. A deterministic date seed is a candidate implementation for repeatable daily selection but is not yet accepted as the only mechanism.

## ADR-006 - Allow roster-wide character selection despite incomplete presentation metadata

**Status:** Accepted

**Decision:** Missing descriptions, artwork, or source links do not remove a character from an eligible game's selection pool. Eligibility is based on the game's combo-trial boundary and roster, not on presentation completeness.

**Rationale:** The user prefers broad discovery across the owned combo-trial games and accepts that supporting metadata will be richer for some characters than others.

**Consequences:** The challenge card must handle missing fields explicitly. The data model must distinguish a missing description or image from an unverified or invalid trial entry.

## ADR-007 - Curate content at build time with provenance

**Status:** Accepted

**Decision:** Character descriptions, artwork references, and source credits live in a versioned challenge catalog. The application does not scrape wikis or image sites during a page request.

**Rationale:** Build-time curation makes the site predictable, avoids runtime dependency on wiki availability and rate limits, and gives each paraphrase and image a reviewable provenance record.

**Consequences:** New characters or corrected metadata require a catalog update and redeploy. Missing fields remain valid catalog states and receive explicit UI fallbacks.

## ADR-008 - Include playable DLC and guest characters with in-game trials

**Status:** Accepted

**Decision:** A character is eligible when it is part of the game's supported playable roster and the game provides combo trials for that character, including DLC and guest characters.

**Rationale:** The user wants broad discovery across each included game while preserving the promise that the challenge can be completed in the game's own trial mode.

**Consequences:** The catalog must distinguish roster membership from presentation completeness and record trial eligibility independently of description or artwork availability.

## ADR-009 - Use stable game and character routes

**Status:** Accepted

**Decision:** The application provides an index and detail route for every included game and a nested detail route for every included character. Historical dates link to those stable character routes rather than to date-specific pages, popups, or modals.

**Rationale:** Stable content pages are easier to revisit, share, expand, and maintain than generated historical pages tied to individual dates.

**Consequences:** Slugs and catalog records must remain stable. Records referenced by history must not be deleted without an archival fallback.

## ADR-010 - Persist immutable daily assignments

**Status:** Accepted

**Decision:** Store one daily assignment per Central-time calendar date, keyed by date, game slug, and character slug. The history route reads stored rows and never regenerates old dates from the current catalog.

**Rationale:** Adding games, characters, or metadata later must not rewrite the user's recommendation history.

**Consequences:** Local development uses SQLite. Vercel deployment requires a durable external database, provisioned through a Vercel Marketplace provider and supplied through `DATABASE_URL`; the exact provider is an implementation gate rather than a product decision.

## ADR-011 - Keep completion tracking out of version 1

**Status:** Accepted

**Decision:** Version 1 records recommendations but does not provide a complete or incomplete status for challenges.

**Rationale:** The learning goal is the randomizer and content navigation; completion state would add user identity and persistence semantics without being required for the core value.

**Consequences:** The history page describes what was recommended, not what was completed. Completion status remains a future promotion from `Ideas.md`.

## ADR-012 - Manual rerolls are browser-local alternates

**Status:** Accepted

**Decision:** A manual reroll is held in a short-lived browser cookie, is ignored after the Central-time day changes, and does not create or modify a daily-assignment row.

**Rationale:** This preserves the stable daily challenge without requiring accounts or storing personal reroll history.

**Consequences:** A reroll is not shared across browsers or visitors. The home page must provide a direct way back to today's challenge.

## ADR-013 - Use the named Supabase project for deployed history

**Status:** Accepted

**Decision:** Production history uses the Supabase Postgres project `elrngwxjmmjfpdedesha` for `daily-combo-trials`. Vercel receives its pooled connection string through the server-only `DATABASE_URL` environment variable.

**Rationale:** The user selected Supabase for durable storage and supplied a project owned by a separate Supabase account from the CLI session. Keeping the database connection in Vercel environment settings preserves that account boundary and avoids publishing credentials.

**Consequences:** The repository can be tested locally with SQLite. The production deployment cannot be considered durable until the other Supabase account supplies the connection string and the deployed app successfully writes a daily assignment.

## ADR-014 - Capture the deployment credential through a private local wizard

**Status:** Accepted

**Decision:** When the user is away from the computer, the local FastAPI app may expose `/setup` through Tailscale Serve on a separate HTTPS port. The page accepts Supabase's placeholder connection URI and a separate password, combines and URL-encodes them server-side, encrypts the completed URI with the current Windows user's DPAPI profile, writes it to ignored local data, and displays only redacted connection metadata. The setup route is disabled on Vercel and is not part of the public product navigation.

**Rationale:** The missing production value is account-owned and cannot be safely requested through chat. Tailscale Serve provides a private HTTPS path from the user's phone while keeping the local listener on loopback; DPAPI avoids a plaintext credential file.

**Consequences:** The user still completes provider dashboard authentication, then can paste the copied placeholder URI and enter the password separately. The agent can later read the encrypted value locally for a Vercel environment handoff without printing it. A process running as the same Windows user remains within the DPAPI trust boundary, so the setup page should be disabled after one-time use when practical.

## ADR-015 - Gate two browser analytics providers to canonical production

**Status:** Accepted implementation; activation and collection verification pending.

**Decision:** Keep FastAPI/Jinja, Vercel hosting, Supabase, and the public URL.
Use one Python request gate and shared template inclusion for automatic Vercel
pageviews and Uppercut Labs Cloudflare non-proxied Web Analytics pageviews and
performance. A small plain JavaScript file initializes Vercel's documented queue
and beforeSend filter. No npm application toolchain, manual pageviews, new
identifiers/cookies, database, DNS changes, or Cloudflare path Rules are added.

**Boundaries:** Require `WEB_ANALYTICS_ENABLED=1`, system `VERCEL_ENV=production`,
and hostname `daily-combo-trials.vercel.app`; exclude `/setup` and descendants
with no-referrer responses while preserving Vercel setup denial. Missing
`CLOUDFLARE_WEB_ANALYTICS_TOKEN` omits only Cloudflare. Set application variables
only in Vercel Production. Never set system variables manually.

**Events and entitlement:** `VERCEL_CUSTOM_EVENTS_ENABLED` defaults off. The
approved hooks are `randomize` and `back_to_daily` on form submit, `open_history`
on either History link, and `outbound_source_click` on curated source activation.
Only outbound events have properties: normalized `host` and semantic `kind`
(`description_source`, `artwork_source`, `game_reference`, `combined_source`).
Collapsed links emit once. Events are best-effort attempts, not completed trials.
The September 5, 2026 account check confirms devint Hobby: 50,000 monthly events,
one-month reporting window, no custom events. Activation remains pending an
owner decision; no paid change or substitute provider is authorized.

**Verification and rollback:** Isolated SQLite/fixed-time tests cover gates and
rendering; intercepted browser tests cover event delivery and normal navigation.
Live network acceptance and each dashboard must be reported separately, with
collection start recorded only when observed. Keep provider totals separate and
never backfill unmeasured traffic. Disable with the master switch and redeploy;
pre-change deployment is `dpl_G9oGRKsWPYBDPLrYKZry8p4dwsvT`, commit `2092379`.
README records rollout evidence and remaining account/plan blockers.
