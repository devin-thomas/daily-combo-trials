# CTR-003 - Home challenge and browser-local reroll

## Goal

Make the daily challenge immediately usable from the home page and add a temporary alternate flow.

## Scope

- Render today's challenge with game, character, description, art, and sources.
- Add `POST /randomize` and `POST /daily`.
- Store the alternate in a short-lived secure cookie without personal data.
- Distinguish daily and temporary states in copy and navigation.

## Acceptance Criteria

- The home page shows the stored daily assignment by default.
- Randomize shows an alternate without modifying the daily database row.
- Returning to today's challenge clears the alternate.
- The alternate is ignored after a Central-time day change.
- Missing artwork and description have visible, concise fallbacks.

## Dependencies

CTR-002.
