# 03: Crawl candidates' games into population rows

**Status:** ready-for-agent

**Blocked by:** 02

**What to build:** For each candidate (by mastery points), list ranked solo match ids since `since`, call
`DataLayer.game_pick` (match only, cached) and, for focus-champion games, `match_with_timeline` + `rows.game_row` from
that player's point of view. Add `tier` (from the ladder) and `player` (salted hash of the puuid; salt in `.env`, never
committed) to each row. Store rows under `data/` only.

CLI: `python -m champion_stats.population Lillia --since 2026-10-08 --hours 3` (budget by time or `--max-requests`).
Interleaving discovery (02) and crawling is fine: crawl a candidate's games as soon as they're found.

- [ ] Duplicate matches skipped; remakes excluded (game_row already does)
- [ ] Only rows whose patch is the current or previous patch kept (patch from `gameVersion`)
- [ ] No puuid, Riot ID or summoner name in any row or output file
- [ ] Resumable; progress shows players, matches fetched, focus games kept, requests used, games per hour
- [ ] Tested with a fake client

## Comments
