"""Integration checks for a disposable local PostgreSQL security-test database."""

from collections.abc import Iterator
from datetime import datetime, timezone
import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, ProgrammingError
from sqlalchemy.schema import CreateTable

from combo_site.catalog import Catalog, Character, Game
from combo_site.database import DailyAssignment, Database


API_ROLES = ("anon", "authenticated")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "20260908_secure_daily_assignments.sql"
CATALOG = Catalog(games=(Game(
    slug="test-game", title="Test Game", steam_appid=None, trial_source_url=None,
    characters=(Character(slug="test-character", name="Test Character"),),
),))


@pytest.fixture
def postgres() -> Iterator[tuple[Engine, URL]]:
    raw_url = os.getenv("TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("TEST_POSTGRES_URL is not set")
    try:
        url = make_url(raw_url)
    except (ArgumentError, ValueError):
        pytest.fail("TEST_POSTGRES_URL must be a valid PostgreSQL URL", pytrace=False)
    if (
        url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "daily_combo_trials_security_test"
        or url.username != "postgres"
        or url.query
    ):
        pytest.fail(
            "Refusing destructive tests: use postgres on a loopback host, database "
            "daily_combo_trials_security_test, and no URL query parameters",
            pytrace=False,
        )

    url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    try:
        with engine.begin() as connection:
            identity = connection.exec_driver_sql(
                "SELECT current_user, current_database(), "
                "pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
            ).one()
            assert tuple(identity) == ("postgres", "daily_combo_trials_security_test", "postgres")
            existing_roles = connection.exec_driver_sql(
                "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
            ).all()
            if existing_roles:
                pytest.fail("Use a disposable PostgreSQL instance without preexisting API roles")
            connection.exec_driver_sql("DROP TABLE IF EXISTS public.daily_assignments")
            connection.exec_driver_sql(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                "GRANT ALL ON TABLES TO PUBLIC"
            )
        try:
            yield engine, url
        finally:
            with engine.begin() as connection:
                connection.exec_driver_sql("DROP TABLE IF EXISTS public.daily_assignments")
                connection.exec_driver_sql(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                    "REVOKE ALL ON TABLES FROM PUBLIC"
                )
                roles = connection.exec_driver_sql(
                    "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
                ).scalars().all()
                for role in roles:
                    connection.exec_driver_sql(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                        f"REVOKE ALL ON TABLES FROM {role}"
                    )
                    connection.exec_driver_sql(f"REVOKE ALL ON SCHEMA public FROM {role}")
                    connection.exec_driver_sql(f"DROP ROLE {role}")
    finally:
        engine.dispose()


def _create_api_roles(engine: Engine) -> None:
    with engine.begin() as connection:
        for role in API_ROLES:
            connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
            connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
            connection.exec_driver_sql(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                f"GRANT ALL ON TABLES TO {role}"
            )


def _assert_secured(engine: Engine, *, api_roles: bool = True) -> None:
    with engine.connect() as connection:
        security = connection.exec_driver_sql(
            "SELECT relrowsecurity, relforcerowsecurity, "
            "(SELECT count(*) FROM pg_policy WHERE polrelid = c.oid), "
            "(SELECT count(*) FROM aclexplode(c.relacl) WHERE grantee = 0) "
            "FROM pg_class c WHERE c.oid = 'public.daily_assignments'::regclass"
        ).one()
        assert tuple(security) == (True, False, 0, 0)
        if api_roles:
            for role in API_ROLES:
                for privilege in PRIVILEGES:
                    assert not connection.scalar(text(
                        "SELECT has_table_privilege(:role, 'public.daily_assignments', :privilege)"
                    ), {"role": role, "privilege": privilege}), (role, privilege)


@pytest.mark.parametrize("api_roles", [False, True])
def test_new_table_is_private_and_existing_startup_emits_no_ddl(
    postgres: tuple[Engine, URL], api_roles: bool,
) -> None:
    engine, url = postgres
    if api_roles:
        _create_api_roles(engine)
    database = Database(url.render_as_string(hide_password=False))
    try:
        _assert_secured(engine, api_roles=api_roles)
        with database.session() as session:
            first = database.get_or_create_daily(session, "2026-09-08", CATALOG)
            again = database.get_or_create_daily(session, "2026-09-08", CATALOG)
            assert again.day == first.day
            assert [(row.day, row.game_slug, row.character_slug) for row in database.list_daily(session)] == [
                ("2026-09-08", "test-game", "test-character")
            ]
    finally:
        database.close()

    statements: list[str] = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lstrip().upper())

    event.listen(Engine, "before_cursor_execute", record_statement)
    try:
        reopened = Database(url.render_as_string(hide_password=False))
        reopened.close()
    finally:
        event.remove(Engine, "before_cursor_execute", record_statement)
    assert statements
    assert not any(statement.startswith(("ALTER ", "REVOKE ", "DO ", "CREATE ")) for statement in statements)
    _assert_secured(engine, api_roles=api_roles)


def test_migration_is_repeatable_and_preserves_existing_history(postgres: tuple[Engine, URL]) -> None:
    engine, _url = postgres
    _create_api_roles(engine)
    with engine.begin() as connection:
        # Direct CreateTable deliberately reproduces the old unsecured bootstrap.
        connection.execute(CreateTable(DailyAssignment.__table__))
        connection.execute(DailyAssignment.__table__.insert().values(
            day="2026-09-06", game_slug="test-game", character_slug="test-character",
            created_at=datetime(2026, 9, 6, 12, tzinfo=timezone.utc),
        ))
        before = connection.exec_driver_sql("SELECT * FROM public.daily_assignments ORDER BY day").all()
        assert not connection.exec_driver_sql(
            "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.daily_assignments'::regclass"
        ).scalar_one()
        assert connection.exec_driver_sql(
            "SELECT has_table_privilege('anon', 'public.daily_assignments', 'TRUNCATE')"
        ).scalar_one()

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        for _ in range(2):
            connection.exec_driver_sql(MIGRATION.read_text(encoding="utf-8"), execution_options={"no_parameters": True})
    _assert_secured(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT * FROM public.daily_assignments ORDER BY day").all() == before


def test_rls_still_blocks_clients_if_dml_grants_are_reintroduced(postgres: tuple[Engine, URL]) -> None:
    engine, url = postgres
    _create_api_roles(engine)
    database = Database(url.render_as_string(hide_password=False))
    try:
        with database.session() as session:
            database.get_or_create_daily(session, "2026-09-08", CATALOG)
        for role in API_ROLES:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.exec_driver_sql(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.daily_assignments "
                        "TO anon, authenticated"
                    )
                    connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    assert connection.exec_driver_sql("SELECT * FROM public.daily_assignments").all() == []
                    assert connection.exec_driver_sql(
                        "UPDATE public.daily_assignments SET game_slug = 'tampered'"
                    ).rowcount == 0
                    assert connection.exec_driver_sql("DELETE FROM public.daily_assignments").rowcount == 0
                    with pytest.raises(ProgrammingError) as error:
                        connection.exec_driver_sql(
                            "INSERT INTO public.daily_assignments VALUES "
                            "('2026-09-09', 'tampered', 'tampered', now())"
                        )
                    assert error.value.orig.sqlstate == "42501"
                finally:
                    transaction.rollback()
        _assert_secured(engine)
        with database.session() as session:
            assert [(row.day, row.game_slug) for row in database.list_daily(session)] == [
                ("2026-09-08", "test-game")
            ]
    finally:
        database.close()
