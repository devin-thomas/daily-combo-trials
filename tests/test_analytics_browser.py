"""Offline browser checks; use an existing Node + Playwright installation.

Set NODE_PATH to the installed Playwright node_modules directory when necessary.
ANALYTICS_BROWSER_REQUIRED=1 makes missing tooling fail instead of skipping.
No packages or browser binaries are downloaded by this test.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from combo_site import main
from combo_site.database import Database
from combo_site.secret_store import SecretStore


ROOT = Path(__file__).resolve().parents[1]
HOST = "daily-combo-trials.vercel.app"


def test_analytics_browser_offline(tmp_path, monkeypatch):
    node = shutil.which("node")
    probe = subprocess.run(
        [node, "-e", "require('playwright')"], capture_output=True, text=True,
    ) if node else None
    if probe is None or probe.returncode:
        reason = "Browser analytics tests require existing Node and Playwright (set NODE_PATH)."
        if os.environ.get("ANALYTICS_BROWSER_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'unused.sqlite3'}")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("WEB_ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("CLOUDFLARE_WEB_ANALYTICS_TOKEN", "offline-test-token")
    database = Database(f"sqlite:///{tmp_path / 'browser.sqlite3'}")
    app = main.create_app(
        database=database,
        now_provider=lambda: datetime(2026, 9, 5, 17, tzinfo=timezone.utc),
        secret_store=SecretStore(tmp_path / "secrets.dpapi"),
    )
    fixtures = {}
    try:
        with TestClient(app, base_url=f"https://{HOST}") as client:
            client.post("/daily")
            daily = client.get("/").text
            client.post("/randomize")
            alternate = client.get("/").text
            game = app.state.catalog.games[0]
            character_path = next(
                f"/games/{item.slug}/characters/{character.slug}"
                for item in app.state.catalog.games
                for character in item.eligible_characters
                if 'Description and artwork source' in client.get(
                    f"/games/{item.slug}/characters/{character.slug}"
                ).text
            )
            paths = ["/history", "/games", f"/games/{game.slug}", character_path]
            fixtures = {
                "daily": daily,
                "alternate": alternate,
                "pages": {path: client.get(path).text for path in paths},
                "characterPath": character_path,
            }
    finally:
        database.close()
    fixture_path = tmp_path / "browser-fixtures.json"
    fixture_path.write_text(json.dumps(fixtures), encoding="utf-8")
    result = subprocess.run(
        [node, str(ROOT / "tests/analytics_browser.cjs"), str(fixture_path), str(ROOT)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode and "Executable doesn't exist" in result.stderr:
        if os.environ.get("ANALYTICS_BROWSER_REQUIRED") != "1":
            pytest.skip("Playwright browser binary is missing; install tooling separately.")
    assert result.returncode == 0, result.stdout + result.stderr
