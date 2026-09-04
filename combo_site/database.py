from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, String, create_engine, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .catalog import Catalog
from .selection import ChallengeRef, choose_challenge


class Base(DeclarativeBase):
    pass


class DailyAssignment(Base):
    __tablename__ = "daily_assignments"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    game_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    character_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _database_url(raw_url: str | None) -> str:
    if raw_url:
        if raw_url.startswith("postgres://"):
            return "postgresql+psycopg://" + raw_url.removeprefix("postgres://")
        if raw_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + raw_url.removeprefix("postgresql://")
        return raw_url

    if os.getenv("VERCEL"):
        raise RuntimeError("DATABASE_URL is required for a Vercel deployment")
    db_path = Path(__file__).resolve().parent.parent / "data" / "history.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


class Database:
    def __init__(self, raw_url: str | None = None) -> None:
        url = _database_url(raw_url or os.getenv("DATABASE_URL"))
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        else:
            # Supabase transaction poolers do not support prepared statements.
            connect_args = {"prepare_threshold": None}
        self.engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def get_or_create_daily(
        self,
        session: Session,
        day: str,
        catalog: Catalog,
        rng=None,
    ) -> DailyAssignment:
        existing = session.get(DailyAssignment, day)
        if existing is not None:
            return existing

        selected = choose_challenge(catalog, rng=rng)
        record = DailyAssignment(
            day=day,
            game_slug=selected.game_slug,
            character_slug=selected.character_slug,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            winner = session.get(DailyAssignment, day)
            if winner is None:
                raise
            return winner
        return record

    def list_daily(self, session: Session) -> list[DailyAssignment]:
        return list(session.scalars(select(DailyAssignment).order_by(desc(DailyAssignment.day))))


def assignment_ref(record: DailyAssignment) -> ChallengeRef:
    return ChallengeRef(record.game_slug, record.character_slug)
