# Daily Combo Trials

Daily Combo Trials is a small server-rendered FastAPI site for fighting-game practice. Each Central-time calendar day gets one stored game and character; the challenge is to complete every combo trial for that character.

The project is intentionally simple so the FastAPI pieces stay visible:

- FastAPI routes and redirects
- Jinja2 templates and plain CSS
- Catalog validation and stable game/character URLs
- A browser-local reroll cookie
- SQLite locally and Supabase Postgres on Vercel

## Run locally

Requires Python 3.12 or newer.

~~~powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --reload
~~~

Open http://127.0.0.1:8000. With no DATABASE_URL, local history is stored in data/history.sqlite3.

Run the checks with:

~~~powershell
.venv\Scripts\python -m pytest
~~~

## Private phone setup over Tailscale

When the computer needs a provider value and you are away from it, run the local app on loopback and publish it through Tailscale Serve:

~~~powershell
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8788
tailscale serve --bg --yes --https=8443 http://127.0.0.1:8788
~~~

Open `https://<this-machine>.<your-tailnet>.ts.net:8443/setup` from a phone that is connected to the same tailnet. Paste Supabase's connection URI with `[YOUR-PASSWORD]`, then enter the database password separately; the server combines and URL-encodes them before saving. The setup page is disabled on Vercel and keeps both fields blank after reload. On Windows, the completed value is encrypted with the current user's DPAPI profile and stored in the ignored `data/remote-secrets.dpapi` file. The page shows only redacted host, port, and database metadata.

Inspect `tailscale serve status` first when this machine already serves other applications. The example uses HTTPS port 8443 so the existing HTTPS routes on port 443 remain in place. Use Tailscale Serve, never Funnel, for a credential handoff.

## Project shape

- app.py exposes the FastAPI instance that Vercel discovers.
- combo_site/ contains catalog loading, selection, persistence, and routes.
- data/catalog.json is the versioned build-time catalog.
- templates/ and static/ contain the server-rendered UI.
- static/art/ contains source-derived roster artwork. The supplied 320px `previews/` thumbnails are not used; the checked-in WebP deliveries are sized to preserve detail while staying within Vercel Hobby's 100 MB upload limit.
- download.json and fg.js are local source inputs and remain ignored.

## Supabase production database

The production database is Supabase project elrngwxjmmjfpdedesha, named daily-combo-trials. In the Supabase dashboard, open the project's Connect panel and copy the Transaction pooler connection string for serverless traffic. Keep the password in the connection string private.

Set that value as Vercel's server-only DATABASE_URL for Production and Preview. The application accepts the postgres:// or postgresql:// form Supabase provides and adapts it to the psycopg SQLAlchemy driver.

For local testing against Supabase only, set the variable in the current PowerShell session:

~~~powershell
$env:DATABASE_URL = "postgresql://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres"
.venv\Scripts\python -m uvicorn app:app --reload
~~~

Do not commit a real connection string. .env.example documents the non-secret project reference, and .env.local/.env files are ignored.

## GitHub and Vercel

The intended repository is devin-thomas/daily-combo-trials.

From a clean local checkout:

~~~powershell
git init -b main
git add .
git commit -m "Build Daily Combo Trials"
gh repo create devin-thomas/daily-combo-trials --public --source . --remote origin --push
npx --yes vercel@latest link --yes --project daily-combo-trials
~~~

Import or connect the GitHub repository from the linked Vercel project when automatic deploys from main are desired. A Vercel CLI deployment is also available:

~~~powershell
npx --yes vercel@latest env add DATABASE_URL production
npx --yes vercel@latest env add DATABASE_URL preview
npx --yes vercel@latest --prod
~~~

The first request after Central midnight creates that date's assignment. Supabase makes that history durable across Vercel function instances; no background cron is required for the v1 behavior.

## Production web analytics

Vercel Web Analytics and Cloudflare Web Analytics share one server-side gate.
They load only when `WEB_ANALYTICS_ENABLED=1`, Vercel's system `VERCEL_ENV`
is exactly `production`, and the request hostname is exactly
`daily-combo-trials.vercel.app`. `/setup` and every `/setup/` descendant are
excluded, including denied responses and redirects. These responses send
`Referrer-Policy: no-referrer`. Hosting/security logs are outside this browser
analytics exclusion. Local, preview, and deployment-alias pages load no analytics.

Set only these application variables in the existing project's **Production**
environment, then deploy through its GitHub `main` integration:

| Variable | Value |
| --- | --- |
| `WEB_ANALYTICS_ENABLED` | `1` enables the shared gate; absent or `0` disables both |
| `CLOUDFLARE_WEB_ANALYTICS_TOKEN` | Actual generated site beacon token from Uppercut Labs |
| `VERCEL_CUSTOM_EVENTS_ENABLED` | `0`; use `1` only after confirming existing Pro/Enterprise entitlement |

Do not manually set Vercel system variables. Confirm automatic system-variable
exposure in project settings and the production gate in the deployed HTML.
Missing Cloudflare configuration omits its beacon while allowing Vercel pageviews.
The public beacon token is serialized safely into HTML; account credentials must
never be included. No application dependencies or build step are needed.

Enable Web Analytics on the existing Vercel project. This plain-HTML integration
initializes `window.va` and `beforeSend` before the supported legacy
`/_vercel/insights/script.js` route loads. The filter rejects setup paths and
unexpected hostnames. The provider collects automatic pageviews; the app sends
no manual pageviews. Verify the script response after every analytics rollout.

Explicitly select **Uppercut Labs** in Cloudflare and reuse or create the exact
hostname as a **non-proxied Web Analytics site**. Use its generated beacon token.
Do not alter DNS, hosting, domains, proxy settings, or configure path Rules.
Cloudflare supplies standard pageview/performance reporting only.

The four implemented Vercel hooks are disabled by default:

| Event | Interaction | Custom properties |
| --- | --- | --- |
| `randomize` | Randomize form submission, including keyboard | None |
| `back_to_daily` | Back to today's challenge form submission | None |
| `open_history` | History navigation link or recommendation-history card | None |
| `outbound_source_click` | Curated source/reference link activation | `host`, `kind` |

Outbound hostnames are lowercase with trailing dot and leading `www.` removed;
`kind` is `description_source`, `artwork_source`, `game_reference`, or
`combined_source`. Collapsed links emit one event. Footer/social links and
ordinary game/character navigation emit no custom events. Events measure
interaction attempts, never practice completion. Delivery is best effort and
does not delay or replace navigation/forms. Disabled hooks queue no custom calls.

On September 5, 2026, the linked team `devint` was rechecked as **Hobby**:
50,000 monthly analytics events across the team and a one-month reporting window;
custom events require Pro/Enterprise. No upgrade, trial, payment, or add-on is
authorized. Custom-event activation remains pending an owner decision.
See [Vercel pricing](https://vercel.com/docs/analytics/limits-and-pricing),
[HTML setup](https://vercel.com/docs/analytics/quickstart), and
[Cloudflare setup](https://developers.cloudflare.com/web-analytics/get-started/).

### Verification and rollback

Run `.venv/bin/python -m pytest` (or the Windows command above). All analytics
tests use temporary SQLite and controlled time, never Supabase. The existing
DPAPI encryption test requires Windows; on other systems it currently fails
because that store intentionally rejects non-Windows platforms. To run the
portable suite, use `-k 'not test_remote_setup_wizard_encrypts_and_redacts_database_url'`.
For browser checks, use an existing Node/Playwright installation and set
`NODE_PATH` to its `node_modules` directory if needed. Run
`ANALYTICS_BROWSER_REQUIRED=1 .venv/bin/python -m pytest tests/test_analytics_browser.py -q`.
This uses Node only as test tooling, not as an application dependency or build
step. No tooling is downloaded by the tests. Without installed browser tooling,
the default suite explicitly skips this check; the required flag makes it fail.

Keep local test provider requests intercepted. For the live smoke test, visit
the canonical homepage once, then one public history page; confirm each script
returns JavaScript and both providers' collection requests succeed. Check the
two dashboards separately. Use HTTP-only requests to verify setup denial and
alias exclusion without adding pageviews. Distinguish network acceptance from
dashboard confirmation; reporting delay is unverified, not success.

Record the first observed collection timestamp; do not backfill launch traffic,
interpret runtime requests as visitors, add the providers' totals together, or
expect their counts to agree. Custom events need a separate live check of all
four names only after existing entitlement permits activation.

To disable both integrations, set `WEB_ANALYTICS_ENABLED=0` in Production and
redeploy once. The pre-analytics rollback point is commit `2092379`, deployment
`dpl_G9oGRKsWPYBDPLrYKZry8p4dwsvT` (September 5, 2026). The public URL remains
https://daily-combo-trials.vercel.app.

### September 5, 2026 rollout status

- Uppercut Labs is uniquely identified as account
  `f81d8a09a3b225b740c17f5a39f6cf80`. Its existing Wrangler OAuth credential
  cannot list Web Analytics sites (API error 10405: method not allowed for this
  authentication scheme). Dashboard sign-in is needed to reuse/create the exact
  non-proxied site and retrieve the actual beacon token.
- The Vercel connector confirms project `prj_AB5XGQQND1us6P9WwYLMigoieveh`
  under Hobby team `devint`. Dashboard and CLI are signed out; production
  variables and Web Analytics enablement cannot yet be confirmed or updated.
- The existing production legacy script route returned HTTP 200 with
  `application/javascript`. This is script availability, not proof of collection.
- Local validation: 30 analytics server cases and four offline Chromium scenarios
  pass. The portable suite passes; the existing Windows DPAPI test fails on macOS,
  also reproduced against the pre-change application code.
- Browser fixtures use isolated SQLite. An initial harness attempt used a mocked
  303 whose redirect could escape interception and request the pre-change public
  homepage once; it was replaced with a fully fulfilled response before the
  successful runs. No real provider events were generated by the passing tests.
- Both providers' live pageview collection remains **blocked** by configuration
  access; dashboard confirmation is **unverified**. All four events are
  **implemented but disabled**, with live activation additionally blocked by Hobby.
  Collection start has not been observed. The full analytics objective is pending.
