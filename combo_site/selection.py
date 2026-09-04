from __future__ import annotations

from dataclasses import dataclass
import random

from .catalog import Catalog


@dataclass(frozen=True)
class ChallengeRef:
    game_slug: str
    character_slug: str

    @property
    def key(self) -> tuple[str, str]:
        return self.game_slug, self.character_slug


def choose_challenge(
    catalog: Catalog,
    rng: random.Random | random.SystemRandom | None = None,
    exclude: ChallengeRef | None = None,
) -> ChallengeRef:
    """Choose a game uniformly, then a character uniformly within that game."""

    random_source = rng or random.SystemRandom()
    if not catalog.games:
        raise ValueError("Cannot choose from an empty catalog")

    selected_game = random_source.choice(catalog.games)
    eligible_characters = selected_game.eligible_characters
    if not eligible_characters:
        raise ValueError(f"Game {selected_game.slug!r} has no eligible characters")
    selected_character = random_source.choice(eligible_characters)
    selected = ChallengeRef(selected_game.slug, selected_character.slug)

    if exclude is None or selected.key != exclude.key or len(catalog.candidates) <= 1:
        return selected

    alternatives = tuple(
        (game, character)
        for game, character in catalog.candidates
        if (game.slug, character.slug) != exclude.key
    )
    alternative_game = random_source.choice(tuple(game for game in catalog.games if game.eligible_characters))
    alternative_characters = tuple(
        character for character in alternative_game.eligible_characters
        if (alternative_game.slug, character.slug) != exclude.key
    )
    if alternative_characters:
        return ChallengeRef(alternative_game.slug, random_source.choice(alternative_characters).slug)

    fallback_game, fallback_character = random_source.choice(alternatives)
    return ChallengeRef(fallback_game.slug, fallback_character.slug)
