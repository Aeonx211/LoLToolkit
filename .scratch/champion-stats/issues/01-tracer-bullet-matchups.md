# 01: Tracer bullet: Matchups with click-to-filter

**What to build:** On a new Champion Stats tab, enter a Riot ID and focus champion, click Load, and see the backfill progress and then a header summary and the Matchups section (enemy champion in each role, with the jungle matchup first). Clicking any row adds it to the filter stack and every table recalculates. Ranked solo only for now.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Backfill pages the player's solo match IDs, fetches each candidate without its timeline, keeps only focus-champion games (fetching their timelines), stops at 100 kept games or end of history, and never refetches stored matches (tested with a fake client)
- [ ] Game row extraction gives match id, patch, queue, start, duration, win, KDA, CS, and ally/enemy champion per role; remakes give no row; a missing role is left out of the role keys (tested with synthetic games)
- [ ] Web UI job streams backfill progress and returns the game rows
- [ ] Header summary: games, W–L, win %, average KDA, average CS for the filtered slice
- [ ] Cut rows show games, W–L, win %, pick rate, delta vs slice; default sort by Wilson lower bound; rows under 5 games greyed but clickable
- [ ] Clicking a row toggles it in the filter stack; chips with x and "clear all"; "N games match" banner; rows that would leave zero games are disabled
- [ ] Checked by driving the tab with Playwright against fixture rows
