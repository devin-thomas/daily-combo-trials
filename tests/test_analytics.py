from datetime import datetime, timezone
from html.parser import HTMLParser
import json

from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from combo_site import main
from combo_site.database import Database
from combo_site.secret_store import SecretStore


HOST = "daily-combo-trials.vercel.app"
VERCEL_SCRIPT = "/_vercel/insights/script.js"
CLOUDFLARE_SCRIPT = "https://static.cloudflareinsights.com/beacon.min.js"


class ScriptParser(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.scripts = []
        self.current = None
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = {"attrs": dict(attrs), "text": ""}
            self.scripts.append(self.current)

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None


def assert_no_analytics(document):
    for marker in (
        "analytics.js", VERCEL_SCRIPT, CLOUDFLARE_SCRIPT,
        "web-analytics-config", "window.va", "cloudflareinsights.com",
    ):
        assert marker not in document


@pytest.fixture
def analytics_client(tmp_path, monkeypatch):
    # Explicit SQLite and fixed challenge time keep all requests isolated from Supabase.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'unused.sqlite3'}")
    monkeypatch.setenv("WEB_ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("CLOUDFLARE_WEB_ANALYTICS_TOKEN", "test-beacon-token")
    monkeypatch.delenv("VERCEL_CUSTOM_EVENTS_ENABLED", raising=False)
    database = Database(f"sqlite:///{tmp_path / 'analytics.sqlite3'}")
    app = main.create_app(
        database=database,
        now_provider=lambda: datetime(2026, 9, 5, 17, tzinfo=timezone.utc),
        secret_store=SecretStore(tmp_path / "secrets.dpapi"),
    )
    with TestClient(app, base_url=f"https://{HOST}") as client:
        yield client
    database.close()


def test_public_pages_share_one_integration(analytics_client):
    game = analytics_client.app.state.catalog.games[0]
    character = game.eligible_characters[0]
    for path in (
        "/", "/history", "/games", f"/games/{game.slug}",
        f"/games/{game.slug}/characters/{character.slug}",
    ):
        response = analytics_client.get(path)
        assert response.status_code == 200
        sources = [s["attrs"].get("src", "") for s in ScriptParser(response.text).scripts]
        assert sources.count(VERCEL_SCRIPT) == 1
        assert sources.count(CLOUDFLARE_SCRIPT) == 1
        assert sum(src.endswith("/static/analytics.js") for src in sources) == 1
        assert sum(src.endswith("/static/site.js") for src in sources) == 1
        assert "data-analytics-event" not in response.text
        assert "web-analytics-config" not in response.text


@pytest.mark.parametrize("environment", [None, "", "preview", "development", "Production"])
def test_nonproduction_environment_omits_analytics(analytics_client, monkeypatch, environment):
    if environment is None:
        monkeypatch.delenv("VERCEL_ENV", raising=False)
    else:
        monkeypatch.setenv("VERCEL_ENV", environment)
    response = analytics_client.get("/")
    assert response.status_code == 200
    assert_no_analytics(response.text)


@pytest.mark.parametrize("enabled", [None, "0", "true", ""])
def test_master_switch_defaults_off(analytics_client, monkeypatch, enabled):
    if enabled is None:
        monkeypatch.delenv("WEB_ANALYTICS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("WEB_ANALYTICS_ENABLED", enabled)
    assert_no_analytics(analytics_client.get("/").text)


@pytest.mark.parametrize("hostname", ["localhost", "testserver", "daily-combo-trials-alias.vercel.app"])
def test_unexpected_host_omits_analytics(analytics_client, hostname):
    assert_no_analytics(analytics_client.get(f"https://{hostname}/").text)


def test_missing_cloudflare_token_preserves_vercel(analytics_client, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_WEB_ANALYTICS_TOKEN", raising=False)
    response = analytics_client.get("/")
    assert response.status_code == 200
    assert VERCEL_SCRIPT in response.text
    assert "/static/analytics.js" in response.text
    assert CLOUDFLARE_SCRIPT not in response.text
    assert "data-cf-beacon" not in response.text


@pytest.mark.parametrize("path", ["/setup", "/setup/", "/setup/private", "/setup/clear"])
def test_production_setup_stays_denied_and_private(analytics_client, path):
    response = analytics_client.get(path)
    assert response.status_code in {404, 405}
    for item in [*response.history, response]:
        assert item.headers["referrer-policy"] == "no-referrer"
        assert_no_analytics(item.text)


@pytest.mark.parametrize("path,allowed", [
    ("/", True), ("/history", True), ("/setup", False),
    ("/setup/", False), ("/setup/private", False), ("/setup-example", True),
])
def test_request_path_gate(analytics_client, path, allowed):
    request = Request({
        "type": "http", "scheme": "https", "path": path,
        "headers": [(b"host", HOST.encode())], "query_string": b"",
        "server": (HOST, 443),
    })
    assert main._analytics_allowed(request) is allowed


def test_local_private_setup_has_no_analytics(analytics_client, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    analytics_client.app.state.setup_enabled = True
    response = analytics_client.get(
        "http://localhost/setup", headers={"Tailscale-User-Login": "test@example.test"}
    )
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert_no_analytics(response.text)


@pytest.mark.parametrize("value", [None, "0", "true", "1"])
def test_retired_custom_event_flag_has_no_effect(analytics_client, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("VERCEL_CUSTOM_EVENTS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("VERCEL_CUSTOM_EVENTS_ENABLED", value)
    response = analytics_client.get("/")
    assert "web-analytics-config" not in response.text
    assert "data-analytics-event" not in response.text
    assert VERCEL_SCRIPT in response.text
    assert analytics_client.post("/randomize", follow_redirects=False).status_code == 303
    assert analytics_client.get("/").status_code == 200
    assert analytics_client.post("/daily", follow_redirects=False).status_code == 303


def test_beacon_configuration_is_safely_serialized(analytics_client, monkeypatch):
    token = '\"\'></script><script>alert("unsafe")</script>&'
    monkeypatch.setenv("CLOUDFLARE_WEB_ANALYTICS_TOKEN", token)
    response = analytics_client.get("/")
    scripts = ScriptParser(response.text).scripts
    beacons = [s for s in scripts if s["attrs"].get("src") == CLOUDFLARE_SCRIPT]
    assert len(beacons) == 1
    assert beacons[0]["attrs"]["type"] == "module"
    assert json.loads(beacons[0]["attrs"]["data-cf-beacon"])["token"] == token
    assert not any('alert("unsafe")' in s["text"] for s in scripts)
