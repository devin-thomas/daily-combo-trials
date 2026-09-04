# Daily Combo Trials

## Objective

Create a low-complexity, server-rendered FastAPI site that turns the user's curated Steam fighting-game library into a daily combo-trial challenge. Each challenge names one included game and one eligible character and instructs the user to complete that character's in-game combo trials.

The site should feel like a useful FGC practice ritual: visually immediate, character-led, and easy to revisit. It should teach FastAPI routes, templates, validation, cookies, persistence, and deployment to Vercel without introducing a frontend framework.

## Scope

### Required

- Use the supplied `download.json` Steam export and `fg.js` curated game IDs as source inputs.
- Use the 17-game `comboTrialGameAppIds` list in `fg.js` as the initial game boundary.
- Maintain a curated catalog covering every included game's eligible playable roster, including DLC and guest characters when the game provides in-game combo trials.
- Select one game uniformly, then one character uniformly from that game's eligible roster.
- Create one immutable daily assignment per calendar date in the `America/Chicago` time zone.
- Show today's assignment on `/`.
- Provide a browser-local temporary reroll that does not alter today's stored assignment.
- Provide `/history` with stored daily recommendations ordered newest first.
- Link each history row to a stable character page, never to a date-specific detail route.
- Provide routes for the game index, every included game, and every included character.
- Show a paraphrased one-sentence description when curated from a trustworthy source.
- Show official or publisher/developer-hosted art when it can be sourced appropriately.
- Record source and credit links for descriptions and artwork.
- Show concise explicit fallbacks for missing metadata.
- Keep version 1 free of completion tracking, accounts, popups, and modals.

### Excluded

- Steam login or live Steam library synchronization.
- Runtime wiki scraping or runtime image scraping.
- User accounts, social sharing state, leaderboards, and per-user history.
- Completion status, streaks, notes, and progress analytics.
- One route generated for every historical date.

## Platform and stack

- Python 3.12-compatible application code.
- FastAPI with a top-level `app` entrypoint in `app.py` for Vercel discovery.
- Jinja2 templates and CSS; no React, Next.js, or frontend framework.
- SQLite for local development.
- Supabase Postgres through the server-only `DATABASE_URL` for a durable Vercel deployment. The app must not assume that Vercel's function filesystem is a persistent database.
- SQLAlchemy for a small persistence boundary that works with local SQLite and Supabase Postgres.
- Catalog data is versioned in the repository and loaded at application startup.
- A local-only setup route may capture the missing Supabase value over Tailscale Serve and store it with Windows user-bound encryption; the route is disabled on Vercel.

## Data model

### Game

- `slug`: stable URL identifier.
- `title`: display name.
- `steam_appid`: source Steam application ID.
- `trial_source_url`: optional link to a trial or game reference.
- `characters`: ordered list of eligible `Character` records.

### Character

- `slug`: stable identifier within its game.
- `name`: display name.
- `trial_eligible`: boolean; must be true for a challenge candidate.
- `description`: optional one-sentence paraphrase.
- `description_source_url`: optional source link.
- `art_url`: optional official or publisher/developer-hosted image URL.
- `art_source_url`: optional source or credit link.
- `art_alt`: concise accessible description of the image.

Missing description, artwork, or source data is valid metadata state. Missing or false `trial_eligible` is not a challenge candidate.

### DailyAssignment

- `day`: unique `date` representing the Central-time calendar day.
- `game_slug`: stable catalog reference.
- `character_slug`: stable character reference within the game.
- `created_at`: UTC timestamp for auditability.

The app stores the selected identity, not duplicated display text or derived metadata. A unique constraint on `day` prevents more than one daily recommendation.

## Selection behavior

1. Determine the current date in `America/Chicago`.
2. Read that date's `DailyAssignment`.
3. If no row exists, choose an eligible game uniformly, then an eligible character uniformly from that game, insert the row, and read it back.
4. If two requests attempt first creation concurrently, the unique date constraint wins; the losing request rereads the committed row.
5. A daily assignment never changes because the catalog gains games, characters, descriptions, or artwork.

The exact day boundary is midnight Central time. In the absence of a scheduled prewarm, the row is created by the first request after the boundary; all later requests use that row.

## Manual reroll behavior

- `POST /randomize` creates a new browser-local alternate using the same game-first selection rule and excludes the stored daily identity when another candidate exists.
- The alternate is held in a short-lived cookie containing only a random seed or stable catalog identity, never personal data.
- The cookie is ignored after the Central-time day changes.
- The home page labels the alternate as temporary and provides `POST /daily` to clear it and return to today's assignment.
- A reroll never inserts or updates `DailyAssignment`.

## Routes

| Method | Route | Behavior |
|---|---|---|
| GET | `/` | Today's challenge or the active temporary alternate. |
| POST | `/randomize` | Set a browser-local alternate and redirect to `/`. |
| POST | `/daily` | Clear the alternate and redirect to `/`. |
| GET | `/history` | List stored daily recommendations; dates link to stable character pages. |
| GET | `/games` | List every included game. |
| GET | `/games/{game_slug}` | Show one game and links to every eligible character page. |
| GET | `/games/{game_slug}/characters/{character_slug}` | Show one character, trial instruction, metadata, art, and sources. |
| GET | `/setup` | Show the local, tailnet-only provider setup wizard. |
| POST | `/setup` | Combine the Supabase placeholder URI and password, validate the result, encrypt it locally, then redirect. |
| POST | `/setup/clear` | Remove the locally encrypted setup value after a CSRF check. |
| GET | `/static/style.css` | Serve the site stylesheet. |

No route accepts a historical date as a required detail identifier. Unknown game or character slugs return a normal 404 page with a useful navigation link.

## User interface

### Home

- Make the selected character artwork the visual anchor when available.
- Show game, character, challenge instruction, description, and source links without requiring a modal.
- Show whether the card represents today's challenge or a temporary alternate.
- Provide one direct `Randomize` action and, for an alternate, one direct `Back to today's challenge` action.
- Include a compact link to recommendation history and the game index.

### History

- Show one row per stored day, newest first.
- Display the Central-time date, game, and character.
- Link the game/character identity to its stable character route.
- Do not imply that a recommendation was completed.
- If only today exists, say that the history currently contains today's recommendation; do not invent earlier rows.

### Game and character pages

- Game pages provide a browsable character index.
- Character pages are directly addressable and reusable by history links.
- Character pages show a concise trial instruction and available supporting links.
- Missing art uses a deliberate text/shape fallback; missing descriptions use a concise unavailable-state message.

### Copy rules

Apply the installed No Useless Copy skill to all rendered strings:

- Use direct headings and actions.
- Do not expose route names, database fields, internal statuses, or sequence numbers.
- Keep source/credit labels because they provide provenance.
- Keep fallback and error text only when it communicates state or the next useful action.

## External content and provenance

- Descriptions are original one-sentence paraphrases, not copied wiki text.
- Each description has a source URL when sourced.
- Prefer official publisher/developer art or official press assets; preserve an art source/credit URL.
- If an asset cannot be safely or reliably used, omit it and render the explicit fallback rather than hotlinking an unreviewed image.
- External pages are opened by the user through normal links; the app does not depend on them being available at request time.

## Failure behavior

- Empty or malformed catalog data fails during startup with a clear developer-facing error.
- A game with no eligible characters is excluded from the selection pool and reported by catalog validation.
- Missing artwork or description renders a deliberate fallback state.
- Missing source URLs never become broken empty links.
- Database connection or write failures return a safe server error page without raw provider output or credentials.
- Daily race conflicts are retried by rereading the existing assignment.
- Unknown routes return a 404 page linking back to the game index or home.

## Security and privacy

- Do not expose the raw Steam export, Steam playtime, or unused source fields through a route.
- Keep database credentials in server-only environment variables for hosted deployments; the local phone handoff may use the encrypted DPAPI store described below.
- The local setup wizard is disabled when `VERCEL` is present, requires loopback or a Tailscale identity header, uses a short-lived CSRF cookie, accepts Supabase's placeholder URI and a separate password field, URL-encodes the password server-side, and never echoes the completed value.
- On Windows, the setup value is encrypted with DPAPI and stored in ignored `data/remote-secrets.dpapi`; pages show only provider, host, and port metadata.
- Bind the local server to `127.0.0.1` and use Tailscale Serve rather than Funnel or public port forwarding for the wizard.
- Use `HttpOnly`, `SameSite=Lax`, and production `Secure` settings for the reroll cookie.
- Treat catalog source URLs as untrusted external links and render them with safe URL validation.
- Version 1 has no authentication and is intended as a personal utility, even if its Vercel URL is technically shareable.

## Testing

- Catalog validation covers every included game, stable slugs, duplicate names/slugs, and at least one eligible character per game.
- Selection tests prove game-first behavior, character eligibility, exclusion of the daily identity for rerolls, and deterministic injected randomness.
- Persistence tests prove one assignment per Central date, old rows remain unchanged after catalog updates, and concurrent insert conflicts reread the winner.
- Time-zone tests cover ordinary rollover, daylight-saving transitions, and UTC dates that differ from the Central date.
- Route tests cover home, reroll, history, game index/detail, every catalog game, every catalog character, 404s, and missing metadata fallbacks.
- Rendered UI review covers desktop and mobile layouts, keyboard-visible controls, image alt text, source links, and the No Useless Copy checklist.
- Local verification runs the documented test command and starts the application once.

## Definition of done

- All required routes work locally with the supplied catalog.
- Every included game and eligible character has a stable route.
- The current daily assignment is stable across requests and preserved in history.
- Manual rerolls never mutate daily history.
- Metadata provenance and missing-data fallbacks are visible and accurate.
- No raw Steam payload or secrets are published.
- Tests pass and the rendered UI has been reviewed against the copy and responsive requirements.
- Deployment is ready for Vercel after the Supabase project `elrngwxjmmjfpdedesha` is connected through `DATABASE_URL`; no claim of live durability is made without that environment check.
