# 01: Tracer bullet: Matchups with click-to-filter

**What to build:** On a new Champion Stats tab, enter a Riot ID and focus champion, click Load, and see the backfill progress and then a header summary and the Matchups section (enemy champion in each role, with the jungle matchup first). Clicking any row adds it to the filter stack and every table recalculates. Ranked solo only for now.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] Backfill pages the player's solo match IDs, fetches each candidate without its timeline, keeps only focus-champion games (fetching their timelines), stops at 100 kept games or end of history, and never refetches stored matches (tested with a fake client)
- [x] Game row extraction gives match id, patch, queue, start, duration, win, KDA, CS, and ally/enemy champion per role; remakes give no row; a missing role is left out of the role keys (tested with synthetic games)
- [x] Web UI job streams backfill progress and returns the game rows
- [x] Header summary: games, W–L, win %, average KDA, average CS for the filtered slice
- [x] Cut rows show games, W–L, win %, pick rate, delta vs slice; default sort by Wilson lower bound; rows under 5 games greyed but clickable
- [x] Clicking a row toggles it in the filter stack; chips with x and "clear all"; "N games match" banner; rows that would leave zero games are disabled
- [x] Checked by driving the tab with Playwright against fixture rows

## Comments

- Done. Each single-valued cut is computed over the slice filtered by every *other* stack entry, so it keeps listing its alternatives and clicking one swaps the selection. Every shown row therefore has at least one game, which covers "rows that would leave zero games are disabled": such rows are never offered. Multi-valued cuts (e.g. any item, in 03) are computed over the full slice and stack as AND.
- Browser check: Playwright against seeded rows (40 games), with Data Dragon stubbed since the container can't reach it. The script and launcher live in the session scratchpad, not the repo.
