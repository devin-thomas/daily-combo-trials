from datetime import date, datetime, timezone
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import pytest

from combo_site.catalog import Catalog, Character, Game, load_catalog
from combo_site.database import DailyAssignment, Database
from combo_site.main import _central_day, create_app
from combo_site.secret_store import SecretStore
from combo_site.selection import ChallengeRef, choose_challenge


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"


@pytest.fixture
def local_test_dir() -> Path:
    test_root = ROOT / "output" / "pytest"
    test_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="case-", dir=test_root) as directory:
        yield Path(directory)


def make_client(
    test_dir: Path,
    now: datetime | None = None,
    secret_store: SecretStore | None = None,
    base_url: str = "http://testserver",
) -> tuple[TestClient, Database]:
    database = Database(f"sqlite:///{(test_dir / 'history.sqlite3').as_posix()}")
    app = create_app(
        catalog=load_catalog(CATALOG_PATH),
        database=database,
        now_provider=lambda: now or datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc),
        secret_store=secret_store or SecretStore(test_dir / "remote-secrets.dpapi"),
    )
    return TestClient(app, base_url=base_url), database


def test_catalog_contains_all_initial_games_and_playable_rosters() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert len(catalog.games) == 17
    assert all(game.eligible_characters for game in catalog.games)
    assert len(catalog.candidates) > len(catalog.games)


def test_selection_is_game_first_and_respects_exclusion() -> None:
    catalog = Catalog(
        games=(
            Game(
                slug="first-game",
                title="First Game",
                steam_appid=1,
                trial_source_url=None,
                characters=(
                    Character(slug="first-character", name="First Character"),
                    Character(slug="second-character", name="Second Character"),
                ),
            ),
            Game(
                slug="second-game",
                title="Second Game",
                steam_appid=2,
                trial_source_url=None,
                characters=(Character(slug="third-character", name="Third Character"),),
            ),
        )
    )

    class LastChoice:
        def choice(self, values):
            return values[-1]

    selected = choose_challenge(catalog, rng=LastChoice())
    assert selected == ChallengeRef("second-game", "third-character")

    excluded = choose_challenge(
        catalog,
        rng=LastChoice(),
        exclude=ChallengeRef("second-game", "third-character"),
    )
    assert excluded != ChallengeRef("second-game", "third-character")


def test_central_day_uses_timezone_boundary() -> None:
    before_midnight = datetime(2026, 9, 4, 4, 59, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc)

    assert _central_day(lambda: before_midnight) == date(2026, 9, 3)
    assert _central_day(lambda: after_midnight) == date(2026, 9, 4)


def test_home_history_and_stable_character_routes(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    try:
        home = client.get("/")
        assert home.status_code == 200
        assert "Daily Combo Trials" in home.text
        assert "Complete every combo trial for this character." in home.text

        with database.session() as session:
            record = session.get(DailyAssignment, "2026-09-04")
            assert record is not None

        history = client.get("/history")
        assert history.status_code == 200
        assert f"/games/{record.game_slug}/characters/{record.character_slug}" in history.text
        assert "/history/" not in history.text

        game = client.get(f"/games/{record.game_slug}")
        character = client.get(f"/games/{record.game_slug}/characters/{record.character_slug}")
        assert game.status_code == 200
        assert character.status_code == 200
    finally:
        client.close()
        database.close()


def test_every_catalog_game_and_character_has_a_route(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    catalog = load_catalog(CATALOG_PATH)
    try:
        for game in catalog.games:
            game_response = client.get(f"/games/{game.slug}")
            assert game_response.status_code == 200
            for character in game.eligible_characters:
                character_response = client.get(
                    f"/games/{game.slug}/characters/{character.slug}"
                )
                assert character_response.status_code == 200
    finally:
        client.close()
        database.close()


def test_reroll_is_temporary_and_does_not_change_daily_record(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    try:
        client.get("/")

        with database.session() as session:
            before = session.get(DailyAssignment, "2026-09-04")
            assert before is not None
            daily_identity = (before.game_slug, before.character_slug)

        reroll = client.post("/randomize", follow_redirects=False)
        assert reroll.status_code == 303
        alternate = client.get("/")
        assert alternate.status_code == 200
        assert "Temporary alternate" in alternate.text

        with database.session() as session:
            after = session.get(DailyAssignment, "2026-09-04")
            assert after is not None
            assert (after.game_slug, after.character_slug) == daily_identity

        back_to_daily = client.post("/daily", follow_redirects=True)
        assert back_to_daily.status_code == 200
        assert "Daily recommendation" in back_to_daily.text
    finally:
        client.close()
        database.close()


def test_missing_metadata_has_explicit_fallbacks(local_test_dir: Path) -> None:
    catalog = Catalog(
        games=(
            Game(
                slug="fallback-game",
                title="Fallback Game",
                steam_appid=7,
                trial_source_url=None,
                characters=(Character(slug="fallback-character", name="Fallback Character"),),
            ),
        )
    )
    database = Database(f"sqlite:///{(local_test_dir / 'fallback.sqlite3').as_posix()}")
    app = create_app(
        catalog=catalog,
        database=database,
        now_provider=lambda: datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc),
    )

    with TestClient(app) as client:
        response = client.get("/games/fallback-game/characters/fallback-character")

    assert response.status_code == 200
    assert "Artwork unavailable" in response.text
    assert "Description not available." in response.text
    database.close()


def test_remote_setup_wizard_encrypts_and_redacts_database_url(local_test_dir: Path) -> None:
    secret_store = SecretStore(local_test_dir / "remote-secrets.dpapi")
    client, database = make_client(
        local_test_dir,
        secret_store=secret_store,
        base_url="https://testserver",
    )
    database_url = "postgresql://postgres.elrngwxjmmjfpdedesha:phone%40safe@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    headers = {
        "Tailscale-User-Login": "devin-thomas@github",
        "X-Forwarded-Proto": "https",
    }
    try:
        assert client.get("/setup").status_code == 403

        page = client.get("/setup", headers=headers)
        assert page.status_code == 200
        assert "Open the Supabase project" in page.text
        csrf_token = client.cookies.get("daily_combo_setup_csrf")
        assert csrf_token

        invalid = client.post(
            "/setup",
            data={"database_url": "postgresql://postgres:YOUR-PASSWORD@example.test/postgres", "csrf_token": csrf_token},
            headers=headers,
        )
        assert invalid.status_code == 400
        assert database_url not in invalid.text

        saved = client.post(
            "/setup",
            data={"database_url": database_url, "csrf_token": csrf_token},
            headers=headers,
            follow_redirects=False,
        )
        assert saved.status_code == 303
        status = client.get("/setup", headers=headers)
        assert status.status_code == 200
        assert "Ready to hand off" in status.text
        assert "aws-0-us-east-1.pooler.supabase.com" in status.text
        assert database_url not in status.text
        assert secret_store.load_database_url() == database_url
        assert database_url.encode("utf-8") not in secret_store.path.read_bytes()

        csrf_token = client.cookies.get("daily_combo_setup_csrf")
        assert csrf_token
        cleared = client.post(
            "/setup/clear",
            data={"csrf_token": csrf_token},
            headers=headers,
            follow_redirects=False,
        )
        assert cleared.status_code == 303
        assert secret_store.load_database_url() is None
    finally:
        client.close()
        database.close()


def test_unknown_routes_return_navigation_page(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    try:
        response = client.get("/games/not-in-the-catalog")

        assert response.status_code == 404
        assert "Page not found" in response.text
        assert "Browse games" in response.text
    finally:
        client.close()
        database.close()
