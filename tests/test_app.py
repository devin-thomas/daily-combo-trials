from datetime import date, datetime, timezone
from pathlib import Path
import re
import tempfile
import unicodedata

from fastapi.testclient import TestClient
import pytest

from combo_site.catalog import Catalog, Character, Game, load_catalog
from combo_site.database import DailyAssignment, Database
from combo_site.links import (
    collapse_source_links,
    game_reference_label,
    source_brand_name,
    source_icon_name,
)
from combo_site.main import _central_day, create_app
from combo_site.secret_store import SecretStore, compose_database_url
from combo_site.selection import ChallengeRef, choose_challenge


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"


def _webp_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AssertionError(f"Not a WebP file: {path}")

    chunk_type = data[12:16]
    if chunk_type == b"VP8X":
        return (
            1 + int.from_bytes(data[24:27], "little"),
            1 + int.from_bytes(data[27:30], "little"),
        )
    if chunk_type == b"VP8 ":
        marker = data[20:].find(b"\x9d\x01\x2a")
        if marker < 0:
            raise AssertionError(f"WebP frame header missing: {path}")
        frame = 20 + marker + 3
        return (
            int.from_bytes(data[frame : frame + 2], "little") & 0x3FFF,
            int.from_bytes(data[frame + 2 : frame + 4], "little") & 0x3FFF,
        )

    raise AssertionError(f"Unsupported WebP chunk {chunk_type!r}: {path}")


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


def test_compose_database_url_encodes_separate_password() -> None:
    template = "postgresql://postgres.example:[YOUR-PASSWORD]@db.example.test:6543/postgres"

    assert compose_database_url(template, "phone@safe/#?") == (
        "postgresql://postgres.example:phone%40safe%2F%23%3F@db.example.test:6543/postgres"
    )
    assert compose_database_url(
        "postgresql://postgres.example:already%40encoded@db.example.test/postgres"
    ) == "postgresql://postgres.example:already%40encoded@db.example.test/postgres"

    with pytest.raises(ValueError, match="separate password"):
        compose_database_url(template)


def test_catalog_contains_all_initial_games_and_playable_rosters() -> None:
    catalog = load_catalog(CATALOG_PATH)

    assert len(catalog.games) == 17
    assert all(game.eligible_characters for game in catalog.games)
    assert len(catalog.candidates) > len(catalog.games)


def test_catalog_rosters_are_alphabetized_and_every_character_has_art_and_description() -> None:
    catalog = load_catalog(CATALOG_PATH)

    for game in catalog.games:
        names = [character.name for character in game.eligible_characters]
        assert names == sorted(
            names,
            key=lambda name: (
                re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    unicodedata.normalize("NFKD", name)
                    .encode("ascii", "ignore")
                    .decode("ascii")
                    .casefold(),
                ).strip(),
                name.casefold(),
            ),
        )
        for character in game.eligible_characters:
            expected_url = f"/static/art/{game.steam_appid}/{character.slug}.webp"
            assert character.art_url == expected_url
            art_path = ROOT / "static" / expected_url.removeprefix("/static/")
            assert art_path.is_file()
            # The supplied gallery previews are capped at 320px; roster art must not regress to them.
            assert max(_webp_dimensions(art_path)) > 320
            assert character.description
            assert character.description_source_url


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
        assert "Developed by Lil Gohan of Uppercut Labs" in home.text
        assert 'href="https://x.com/gohan__fgc"' in home.text
        assert "/static/brand/uppercut-labs.jpg" in home.text

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


def test_public_copy_has_no_redundant_labels(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    try:
        pages = {
            "home": client.get("/"),
            "history": client.get("/history"),
            "games": client.get("/games"),
            "game": client.get("/games/street-fighter-6"),
            "character": client.get("/games/street-fighter-6/characters/ryu"),
            "missing": client.get("/not-in-the-catalog"),
        }

        assert all("Central time" not in response.text for response in pages.values())
        assert "Daily recommendation" not in pages["home"].text
        assert "See what was recommended on earlier days." not in pages["home"].text
        assert "Open a game, then choose a character." not in pages["home"].text
        assert "Choose a game to browse its trial characters." not in pages["games"].text
        assert "Each date opens the same game and character page you can revisit anytime." not in pages["history"].text
        assert '<p class="kicker">Street Fighter 6</p>' not in pages["character"].text
    finally:
        client.close()
        database.close()


def test_external_links_show_brand_and_keep_game_reference_copy_honest(local_test_dir: Path) -> None:
    client, database = make_client(local_test_dir)
    try:
        character = client.get("/games/street-fighter-6/characters/ryu")
        assert character.status_code == 200
        assert "/static/icons/brands/supercombo.svg" in character.text
        assert "/static/icons/brands/steam.svg" in character.text
        assert character.text.count("/static/icons/lucide-external-link.svg") == 2
        assert "Character source" in character.text
        assert 'aria-label="Description and artwork source - SuperCombo"' in character.text
        assert 'aria-label="Artwork source - SuperCombo"' not in character.text
        assert "Open on Steam" in character.text

        tokon = client.get("/games/marvel-tokon-fighting-souls/characters/carnage")
        assert tokon.status_code == 200
        assert tokon.text.count("/static/icons/lucide-external-link.svg") == 1
        assert "Official game page" in tokon.text
        assert 'aria-label="Description and artwork source; Open game reference - PlayStation"' in tokon.text
        assert tokon.text.count(
            'href="https://www.playstation.com/en-us/games/marvel-tokon-fighting-souls/"'
        ) == 1
        assert "blog.playstation.com/2026/06/02/" not in tokon.text

        tekken_character = client.get(
            "/games/tekken-8/characters/alisa-bosconovitch"
        )
        assert tekken_character.status_code == 200
        assert tekken_character.text.count("/static/icons/lucide-external-link.svg") == 1
        assert "Official fighter page" in tekken_character.text
        assert 'aria-label="Description and artwork source; Open game reference - TEKKEN"' in tekken_character.text
        assert 'href="https://tekken.com/fighters/alisa-bosconovitch"' in tekken_character.text
        assert 'href="https://tekken.com/fighters"' not in tekken_character.text

        tekken = client.get("/games/tekken-8")
        assert tekken.status_code == 200
        assert "Open game reference" in tekken.text
        assert "Open on Steam" not in tekken.text
        assert "/static/icons/brands/tekken.svg" in tekken.text
        assert 'aria-label="Open game reference - TEKKEN"' in tekken.text
    finally:
        client.close()
        database.close()


def test_collapse_source_links_keeps_each_exact_url_once() -> None:
    assert collapse_source_links(
        [
            {"url": "https://example.test/source", "label": "Description source"},
            {"url": "https://example.test/source", "label": "Artwork source"},
            {"url": "https://example.test/game", "label": "Open game reference"},
            {"url": None, "label": "Missing source"},
        ]
    ) == [
        {
            "url": "https://example.test/source",
            "label": "Character source",
            "detail_label": "Description and artwork source",
        },
        {
            "url": "https://example.test/game",
            "label": "Open game reference",
            "detail_label": "Open game reference",
        },
    ]


def test_collapse_source_links_groups_tokon_and_tekken_alternate_urls() -> None:
    assert collapse_source_links(
        [
            {
                "url": "https://www.playstation.com/en-us/games/marvel-tokon-fighting-souls/",
                "label": "Description and artwork source",
            },
            {
                "url": "https://blog.playstation.com/2026/06/02/magneto-green-goblin-carnage-announced-for-marvel-tokon-fighting-souls/",
                "label": "Open game reference",
            },
            {
                "url": "https://tekken.com/fighters/alisa-bosconovitch",
                "label": "Description and artwork source",
            },
            {"url": "https://tekken.com/fighters", "label": "Open game reference"},
        ]
    ) == [
        {
            "url": "https://www.playstation.com/en-us/games/marvel-tokon-fighting-souls/",
            "label": "Official game page",
            "detail_label": "Description and artwork source; Open game reference",
        },
        {
            "url": "https://tekken.com/fighters/alisa-bosconovitch",
            "label": "Official fighter page",
            "detail_label": "Description and artwork source; Open game reference",
        },
    ]


def test_source_brand_mapping_covers_catalog_domains() -> None:
    expected = {
        "https://store.steampowered.com/app/1/": ("brand-steam", "Steam"),
        "https://wiki.supercombo.gg/w/character": ("brand-supercombo", "SuperCombo"),
        "https://blazblue.wiki/wiki/character": ("brand-blazblue", "BlazBlue Wiki"),
        "https://www.dustloop.com/w/character": ("brand-dustloop", "Dustloop"),
        "https://wiki.gbl.gg/w/character": ("brand-gbl", "GBL Wiki"),
        "https://tekken.com/fighters": ("brand-tekken", "TEKKEN"),
        "https://blog.playstation.com/article": ("brand-playstation", "PlayStation"),
        "https://game.capcom.com/fighters": ("brand-capcom", "Capcom"),
        "https://supabase.com/dashboard": ("brand-supabase", "Supabase"),
    }

    for url, (icon_name, brand_name) in expected.items():
        assert source_icon_name(url) == icon_name
        assert source_brand_name(url) == brand_name
        assert (ROOT / "static" / "icons" / "brands" / f"{icon_name.removeprefix('brand-')}.svg").is_file()

    assert game_reference_label("https://store.steampowered.com/app/1/") == "Open on Steam"
    assert game_reference_label("https://tekken.com/fighters") == "Open game reference"


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
        assert "Alternate challenge" in alternate.text
        assert "Temporary alternate" not in alternate.text

        with database.session() as session:
            after = session.get(DailyAssignment, "2026-09-04")
            assert after is not None
            assert (after.game_slug, after.character_slug) == daily_identity

        back_to_daily = client.post("/daily", follow_redirects=True)
        assert back_to_daily.status_code == 200
        assert "Today's challenge" in back_to_daily.text
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
    connection_string = "postgresql://postgres.elrngwxjmmjfpdedesha:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    database_password = "phone@safe/#?"
    database_url = "postgresql://postgres.elrngwxjmmjfpdedesha:phone%40safe%2F%23%3F@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    headers = {
        "Tailscale-User-Login": "devin-thomas@github",
        "X-Forwarded-Proto": "https",
    }
    try:
        assert client.get("/setup").status_code == 403

        page = client.get("/setup", headers=headers)
        assert page.status_code == 200
        assert "Supabase connection | Daily Combo Trials" in page.text
        assert "Open Supabase" in page.text
        assert "Open the Vercel project" not in page.text
        assert "Primary navigation" not in page.text
        assert "Central time" not in page.text
        assert "Private setup" not in page.text
        assert 'placeholder="Supabase database password"' not in page.text
        assert "The saved value stays encrypted on Titan." not in page.text
        assert "[YOUR-PASSWORD]" in page.text
        csrf_token = client.cookies.get("daily_combo_setup_csrf")
        assert csrf_token

        invalid = client.post(
            "/setup",
            data={"database_url": connection_string, "database_password": "", "csrf_token": csrf_token},
            headers=headers,
        )
        assert invalid.status_code == 400
        assert database_url not in invalid.text

        saved = client.post(
            "/setup",
            data={
                "database_url": connection_string,
                "database_password": database_password,
                "csrf_token": csrf_token,
            },
            headers=headers,
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"] == "/setup"
        status = client.get("/setup", headers=headers)
        assert status.status_code == 200
        assert "Saved" in status.text
        assert "aws-0-us-east-1.pooler.supabase.com" in status.text
        assert database_url not in status.text
        assert database_password not in status.text
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
        assert cleared.headers["location"] == "/setup"
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
