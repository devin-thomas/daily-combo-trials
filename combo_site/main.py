from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import random
import secrets
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .catalog import Catalog, Character, Game, load_catalog
from .database import Database, assignment_ref
from .selection import ChallengeRef, choose_challenge


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog.json"
CENTRAL = ZoneInfo("America/Chicago")
REROLL_COOKIE = "combo_trial_reroll"


def _default_catalog() -> Catalog:
    return load_catalog(CATALOG_PATH)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _central_now(now_provider: Callable[[], datetime] | None = None) -> datetime:
    current = (now_provider or _now_utc)()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(CENTRAL)


def _central_day(now_provider: Callable[[], datetime] | None = None) -> date:
    return _central_now(now_provider).date()


def _cookie_seconds_until_midnight(now_provider: Callable[[], datetime] | None = None) -> int:
    current = _central_now(now_provider)
    tomorrow = current.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=CENTRAL)
    return max(60, int((next_midnight - current).total_seconds()))


def _parse_reroll(value: str | None, day: date) -> int | None:
    if not value:
        return None
    cookie_day, separator, raw_seed = value.partition(":")
    if separator != ":" or cookie_day != day.isoformat():
        return None
    try:
        return int(raw_seed)
    except ValueError:
        return None


def _resolve(catalog: Catalog, reference: ChallengeRef) -> tuple[Game, Character]:
    resolved = catalog.get_character(reference.game_slug, reference.character_slug)
    if resolved is None:
        raise RuntimeError(
            f"Stored challenge {reference.game_slug}/{reference.character_slug} is missing from the catalog"
        )
    return resolved


def _challenge_view(catalog: Catalog, reference: ChallengeRef) -> dict[str, object]:
    game, character = _resolve(catalog, reference)
    return {"game": game, "character": character}


def create_app(
    catalog: Catalog | None = None,
    database: Database | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> FastAPI:
    site_catalog = catalog or _default_catalog()
    site_database = database or Database()
    templates = Jinja2Templates(directory=str(ROOT / "templates"))

    app = FastAPI(title="Daily Combo Trials")
    app.state.catalog = site_catalog
    app.state.database = site_database
    app.state.now_provider = now_provider
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    def today_assignment():
        day = _central_day(now_provider)
        with site_database.session() as session:
            record = site_database.get_or_create_daily(session, day.isoformat(), site_catalog)
        return day, record

    @app.get("/", response_class=HTMLResponse, name="home")
    def home(request: Request) -> HTMLResponse:
        day, daily_record = today_assignment()
        daily_ref = assignment_ref(daily_record)
        reroll_seed = _parse_reroll(request.cookies.get(REROLL_COOKIE), day)
        is_alternate = reroll_seed is not None
        active_ref = daily_ref
        if reroll_seed is not None:
            active_ref = choose_challenge(
                site_catalog,
                rng=random.Random(f"{day.isoformat()}:{reroll_seed}"),
                exclude=daily_ref,
            )
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={
                "request": request,
                "day": day,
                "daily": _challenge_view(site_catalog, daily_ref),
                "challenge": _challenge_view(site_catalog, active_ref),
                "is_alternate": is_alternate,
                "game_count": len(site_catalog.games),
            },
        )

    @app.post("/randomize", name="randomize")
    def randomize() -> RedirectResponse:
        response = RedirectResponse(url="/", status_code=303)
        secure = bool(os.getenv("VERCEL") or os.getenv("ENVIRONMENT") == "production")
        day = _central_day(now_provider)
        response.set_cookie(
            key=REROLL_COOKIE,
            value=f"{day.isoformat()}:{secrets.randbits(63)}",
            max_age=_cookie_seconds_until_midnight(now_provider),
            httponly=True,
            samesite="lax",
            secure=secure,
            path="/",
        )
        return response

    @app.post("/daily", name="daily")
    def daily() -> RedirectResponse:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(key=REROLL_COOKIE, path="/")
        return response

    @app.get("/history", response_class=HTMLResponse, name="history")
    def history(request: Request) -> HTMLResponse:
        today_assignment()
        with site_database.session() as session:
            records = site_database.list_daily(session)
        entries = []
        for record in records:
            resolved = site_catalog.get_character(record.game_slug, record.character_slug)
            entries.append(
                {
                    "record": record,
                    "resolved": resolved,
                }
            )
        return templates.TemplateResponse(
            request=request,
            name="history.html",
            context={"request": request, "entries": entries},
        )

    @app.get("/games", response_class=HTMLResponse, name="games")
    def games(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="games.html",
            context={"request": request, "games": site_catalog.games},
        )

    @app.get("/games/{game_slug}", response_class=HTMLResponse, name="game_detail")
    def game_detail(request: Request, game_slug: str) -> HTMLResponse:
        game = site_catalog.get_game(game_slug)
        if game is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(
            request=request,
            name="game.html",
            context={"request": request, "game": game},
        )

    @app.get(
        "/games/{game_slug}/characters/{character_slug}",
        response_class=HTMLResponse,
        name="character_detail",
    )
    def character_detail(request: Request, game_slug: str, character_slug: str) -> HTMLResponse:
        resolved = site_catalog.get_character(game_slug, character_slug)
        if resolved is None:
            raise HTTPException(status_code=404)
        game, character = resolved
        return templates.TemplateResponse(
            request=request,
            name="character.html",
            context={"request": request, "game": game, "character": character},
        )

    @app.exception_handler(404)
    async def not_found(request: Request, _exc) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"request": request},
            status_code=404,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"request": request},
            status_code=422,
        )

    return app


app = create_app()
