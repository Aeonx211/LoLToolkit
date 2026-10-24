# Handoff: Champion Stats (ticket 07 next)

Saved in the repo rather than `/tmp` because cloud containers are reclaimed and the user reads on a phone.

## Where things are

- Spec: `.scratch/champion-stats/spec.md`. Tickets: `.scratch/champion-stats/issues/01..08`. 01–06 are done; 07 (CLI) is next; 08 is for the user on their PC (Riot key).
- Vocabulary: `GLOSSARY.md` (tracked player, focus champion, focus slice, role, matchup, cut, filter stack, rune value, camp pace). Decisions: `docs/adr/0001`, `docs/adr/0002` (filter stack computed in the browser).
- Branch `claude/lillia-jungle-stats-tracker-psjoh1`; no PR yet (don't open one unless asked).

## How it's built (extend, don't redesign)

- `champion_stats/rows.py` `game_row(match, timeline, puuid)` is the only place facts are extracted. Every new cut needs its fields added here, with a test in `tests/test_champion_stats.py` (uses `tests/fixtures.build_match` plus the `lillia_match` helper; player is participant 2, blue jungle).
- `champion_stats/backfill.py` and `service.py` (`load_rows`, `QUEUES` solo/flex/both, `TRACKED_PLAYERS`). The web job is `champion_stats` in `webui/server.py`; it accepts `queue` (solo/flex/both).
- `webui/static/champion_stats.js`: add a cut by pushing to `csCuts()` with `{id, section, title, short, keys(row) -> [keys], label, multi?}` and add the section to `CS_SECTIONS`. Single-valued cuts swap their selection; `multi: true` cuts (any item, individual runes) AND together.
- Item/rune/tree names and rune-value labels come back with the rows under `names` (`service._names`).

## Verifying

- Tests: `python -m unittest discover -t . -s tests` (86 pass).
- Browser: `.scratch/champion-stats/tools/serve_offline.py <port>` starts the UI with Data Dragon stubbed (set `RIOT_API_KEY=fake` and a scratch `TOOLKIT_DATA_DIR`), then `node .scratch/champion-stats/tools/check_tab.js <screenshot dir>` seeds rows into `localStorage` and drives the tab. Extend the seeded rows and assertions for each new cut.
- The cloud environment blocks api.riotgames.com, ddragon.leagueoflegends.com and lolalytics.com. Don't fake real results; real data waits for ticket 08.

## Open notes

- Rune-value labels start as best guesses marked unverified.
- `CLAUDE.md` asks for a one-line PushNotification when a turn ends waiting on the user or a long task finishes.

## Suggested skills

- `tdd` for each ticket's row extraction.
- `domain-modeling` if a new term comes up.
- `code-review` before calling the branch done.
- `implement` to work a ticket end to end.
