# daily-combo-trials

Server-rendered daily fighting-game combo practice site.
One game/character combo challenge per Central-time calendar day.
Python 3.12 + FastAPI + Jinja2, SQLite locally / Supabase Postgres in production, deployed to Vercel.

## Branch naming

Use plain kebab-case with no prefix: `add-game-support`, `fix-daily-rotation`, `update-2xko-art`.
Append `-2`, `-3` if a second branch for the same topic is needed.
No `claude/`, `feat/`, `dev/` or other prefixes.

## Shared assets

Character art is maintained in the `fgc-assets` submodule at `shared/fgc-assets/`.
Run `git submodule update --init` after cloning.
Serve it via FastAPI: `app.mount("/shared-art", StaticFiles(directory="shared/fgc-assets/characters"))`.

## Key paths

- `data/catalog.json` — build-time game/character catalog (source of truth for daily assignments)
- `static/art/` — local character art (to be migrated to submodule)
- `combo_site/` — FastAPI application code
