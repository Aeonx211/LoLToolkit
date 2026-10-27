# Spec: Champion Population

**Status:** ready-for-agent

## Problem Statement

Champion Stats lets me stack filters (enemy jungler, then pet, then 2nd item, then keystone, ...) over my own games, which
lolalytics can't do: it lets you narrow by one condition, once. But my own games run out after one or two filters
(61 Lillia solo games). I want the same tab over a large sample of *other* Lillia players' ranked solo games, so stacked
filters still have games left, and I want to compare my rows against that population.

## Why not scrape lolalytics

lolalytics only publishes aggregates (win rate given one condition). Stacked filters need the joint data, one row per
game, which can't be rebuilt from one-condition aggregates. Its terms also forbid scraping. The Riot API is the only
source of per-game rows, so we crawl it.

## Decisions so far (2026-10-27, from the user)

- **Elo:** Emerald and above (Emerald IV through Challenger), ranked solo (queue 420), NA.
- **Patches:** current and previous patch only.
- **Budget:** a few hours per run, on the user's PC (cloud sessions can't reach Riot). Dev key: 100 requests / 2 min,
  bulk stops at 80%, so about 2,400 requests an hour.
- **Privacy:** the repo is public. The population data stays in gitignored `data/` and is **not committed** for now.
  The phone page is exported on the PC. Revisit later if the user wants an anonymized committed snapshot.
- **Focus champion:** Lillia, but nothing in the code should hard-code her (take `champion` as an argument).

## Shape

1. **Discover players:** page through the Emerald+ ladder. For each player, one champion-mastery call for the focus
   champion: keep them if `lastPlayTime` is at or after the previous patch's start. Order candidates by mastery points
   (heavy players waste fewer match fetches).
2. **Crawl games:** for each candidate, list ranked solo match ids since the previous patch's start; fetch each match
   (no timeline) via `game_pick`; for focus-champion games, fetch the timeline and build a row with the existing
   `rows.game_row(match, timeline, puuid, items)` from that player's point of view. Skip duplicate matches.
3. **Rows:** population rows add `tier` and `player` (a salted hash of the puuid, never the puuid or name).
4. **Page:** the export can show **Me**, **Population**, or both. In "Me" view Δ can be measured against the population's
   win rate for the same cut row, which shows where I underperform the champion, not just which matchups are hard.

## Out of scope

- Other regions, flex queue, other champions' populations (the code should allow them, but we don't test them now).
- Committing population data to the repo.
- Running the crawl in a cloud session.

## Known risks

- **Discovery cost:** most Emerald+ players never play Lillia, and each mastery check costs a request. The pilot
  (ticket 04) measures games per hour before the user commits a long run. The earlier estimate of 400–800 games per
  hour was a guess.
- **One-tricks:** a few heavy players can dominate. The page needs a Players count and an optional per-player cap.
- **Elo mixing:** rows carry `tier` so the page can filter by it.
