# CTR-004 - Game, character, and recommendation-history routes

## Goal

Make every included game and character directly addressable and connect stored dates to stable content pages.

## Scope

- Add `/games`, `/games/{game_slug}`, and `/games/{game_slug}/characters/{character_slug}`.
- Add `/history` with stored daily assignments ordered newest first.
- Add correct 404 handling and navigation.
- Keep history links independent of date-specific routes and modal UI.

## Acceptance Criteria

- The game index lists every included game.
- Every catalog game resolves to a game detail page.
- Every eligible character resolves to a nested stable character page.
- Every history row links to the matching character page.
- History never claims a recommendation was completed.
- Unknown slugs return a useful 404 response.

## Dependencies

CTR-001, CTR-002.
