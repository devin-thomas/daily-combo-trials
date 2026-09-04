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
