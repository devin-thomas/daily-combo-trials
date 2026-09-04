from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


class CatalogError(ValueError):
    """Raised when the challenge catalog cannot be used safely."""


@dataclass(frozen=True)
class Character:
    slug: str
    name: str
    trial_eligible: bool = True
    description: str | None = None
    description_source_url: str | None = None
    art_url: str | None = None
    art_source_url: str | None = None
    art_alt: str | None = None


@dataclass(frozen=True)
class Game:
    slug: str
    title: str
    steam_appid: int
    trial_source_url: str | None
    characters: tuple[Character, ...]

    @property
    def eligible_characters(self) -> tuple[Character, ...]:
        return tuple(character for character in self.characters if character.trial_eligible)

    def get_character(self, slug: str) -> Character | None:
        return next((character for character in self.characters if character.slug == slug), None)


@dataclass(frozen=True)
class Catalog:
    games: tuple[Game, ...]

    def get_game(self, slug: str) -> Game | None:
        return next((game for game in self.games if game.slug == slug), None)

    def get_character(self, game_slug: str, character_slug: str) -> tuple[Game, Character] | None:
        game = self.get_game(game_slug)
        if game is None:
            return None
        character = game.get_character(character_slug)
        return (game, character) if character is not None else None

    @property
    def candidates(self) -> tuple[tuple[Game, Character], ...]:
        return tuple(
            (game, character)
            for game in self.games
            for character in game.eligible_characters
        )


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        raise CatalogError(f"Cannot create a stable slug for {value!r}")
    return slug


def _alphabetical_name_key(value: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip(), normalized


def _require_text(raw: Any, field: str, context: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise CatalogError(f"{context} requires a non-empty {field}")
    return raw.strip()


def _optional_text(raw: Any, field: str, context: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise CatalogError(f"{context} has an invalid {field}")
    return raw.strip()


def _parse_character(raw: Any, game_context: str, index: int) -> Character:
    if isinstance(raw, str):
        name = _require_text(raw, "name", f"{game_context} character {index}")
        raw = {"name": name}
    if not isinstance(raw, dict):
        raise CatalogError(f"{game_context} character {index} must be a string or object")

    name = _require_text(raw.get("name"), "name", f"{game_context} character {index}")
    slug = _require_text(raw.get("slug") or slugify(name), "slug", f"{game_context} character {index}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise CatalogError(f"{game_context} character {name!r} has an invalid slug {slug!r}")

    trial_eligible = raw.get("trial_eligible", True)
    if not isinstance(trial_eligible, bool):
        raise CatalogError(f"{game_context} character {name!r} has a non-boolean trial_eligible")

    return Character(
        slug=slug,
        name=name,
        trial_eligible=trial_eligible,
        description=_optional_text(raw.get("description"), "description", f"{game_context} character {name!r}"),
        description_source_url=_optional_text(
            raw.get("description_source_url"),
            "description_source_url",
            f"{game_context} character {name!r}",
        ),
        art_url=_optional_text(raw.get("art_url"), "art_url", f"{game_context} character {name!r}"),
        art_source_url=_optional_text(
            raw.get("art_source_url"),
            "art_source_url",
            f"{game_context} character {name!r}",
        ),
        art_alt=_optional_text(raw.get("art_alt"), "art_alt", f"{game_context} character {name!r}"),
    )


def load_catalog(path: Path) -> Catalog:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"Unable to read catalog at {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Catalog at {path} is not valid JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise CatalogError("Catalog must contain a games array")

    games: list[Game] = []
    game_slugs: set[str] = set()
    for game_index, raw_game in enumerate(payload["games"], start=1):
        context = f"Game {game_index}"
        if not isinstance(raw_game, dict):
            raise CatalogError(f"{context} must be an object")
        title = _require_text(raw_game.get("title"), "title", context)
        slug = _require_text(raw_game.get("slug") or slugify(title), "slug", context)
        if slug in game_slugs:
            raise CatalogError(f"Duplicate game slug {slug!r}")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise CatalogError(f"{context} has an invalid slug {slug!r}")
        game_slugs.add(slug)

        appid = raw_game.get("steam_appid")
        if not isinstance(appid, int) or appid <= 0:
            raise CatalogError(f"{context} requires a positive integer steam_appid")

        raw_characters = raw_game.get("characters")
        if not isinstance(raw_characters, list) or not raw_characters:
            raise CatalogError(f"{context} requires a non-empty characters array")
        characters = tuple(
            sorted(
                (
                    _parse_character(raw_character, f"{context} {title!r}", character_index)
                    for character_index, raw_character in enumerate(raw_characters, start=1)
                ),
                key=lambda character: _alphabetical_name_key(character.name),
            )
        )
        character_slugs = [character.slug for character in characters]
        if len(character_slugs) != len(set(character_slugs)):
            raise CatalogError(f"{context} {title!r} contains duplicate character slugs")
        if not any(character.trial_eligible for character in characters):
            raise CatalogError(f"{context} {title!r} has no eligible characters")

        games.append(
            Game(
                slug=slug,
                title=title,
                steam_appid=appid,
                trial_source_url=_optional_text(raw_game.get("trial_source_url"), "trial_source_url", context),
                characters=characters,
            )
        )

    if not games:
        raise CatalogError("Catalog must contain at least one game")
    return Catalog(games=tuple(games))
