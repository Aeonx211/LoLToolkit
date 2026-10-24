# Handoff: Champion Stats (ticket 07 next; 08 done)

Saved in the repo rather than `/tmp` because cloud containers are reclaimed and the user reads on a phone.

## Where things are

- Spec: `.scratch/champion-stats/spec.md`. Tickets: `.scratch/champion-stats/issues/01..08`. 01–06 and 08 are done; 07 (CLI) is next. 08 was run on the user's PC against the real API: see its Comments for what real payloads look like and what changed.
- Vocabulary: `GLOSSARY.md` (tracked player, focus champion, focus slice, role, matchup, cut, filter stack, rune value, camp pace). Decisions: `docs/adr/0001`, `docs/adr/0002` (filter stack computed in the browser).
- Branch `claude/lillia-jungle-stats-tracker-psjoh1`; no PR yet (don't open one unless asked).

## How it's built (extend, don't redesign)

- `champion_stats/rows.py` `game_row(match, timeline, puuid)` is the only place facts are extracted. Every new cut needs its fields added here, with a test in `tests/test_champion_stats.py` (uses `tests/fixtures.build_match` plus the `lillia_match` helper; player is participant 2, blue jungle).
- `champion_stats/backfill.py` and `service.py` (`load_rows`, `QUEUES` solo/flex/both, `TRACKED_PLAYERS`). The web job is `champion_stats` in `webui/server.py`; it accepts `queue` (solo/flex/both).
- `webui/static/champion_stats.js`: add a cut by pushing to `csCuts()` with `{id, section, title, short, keys(row) -> [keys], label, multi?}` and add the section to `CS_SECTIONS`. Single-valued cuts swap their selection; `multi: true` cuts (any item, individual runes) AND together.
- Item/rune/tree names and rune-value labels come back with the rows under `names` (`service._names`).

## Verifying

- Tests: `python -m unittest discover -t . -s tests` (96 pass). Test item data in `tests/test_champion_stats.py` is shaped like real Data Dragon 16.20 (tier-2 boots have `into`, Gunmetal Greaves has no Boots tag): keep it that way.
- Browser: `.scratch/champion-stats/tools/serve_offline.py <port>` starts the UI with Data Dragon stubbed (set `RIOT_API_KEY=fake` and a scratch `TOOLKIT_DATA_DIR`), then `node .scratch/champion-stats/tools/check_tab.js <screenshot dir>` seeds rows into `localStorage` and drives the tab. Extend the seeded rows and assertions for each new cut.
- The cloud environment blocks api.riotgames.com, ddragon.leagueoflegends.com and lolalytics.com. Don't fake real results. On the user's PC, `check_tab.js` needs Playwright; with only `playwright-core` installed, launch the installed Chrome (`channel: "chrome"`); Edge failed to start headless.
- Don't run long read queries on `data/toolkit.db` while a backfill is writing ("database is locked").

## Open notes

- Rune-value labels are verified per rune: `VERIFIED_RUNES` in `rune_labels.py` (Triumph, Cash Back, Gathering Storm so far, with the evidence in comments). Others show an "unverified" chip; unlabelled slots with values show as raw `varN`.
- Real data: Aeoen#NA1 has 61 Lillia ranked solo games in full history (838 solo games), all jungle.
- Waiting on the user: should camp pace compare against the enemy jungler (spec/glossary) or the enemy in your role (as built)? Should the backfill cap how many games it scans? Code-review follow-ups are listed in ticket 08's Comments.
- `CLAUDE.md` asks for a one-line PushNotification when a turn ends waiting on the user or a long task finishes.

## Suggested skills

- `tdd` for each ticket's row extraction.
- `domain-modeling` if a new term comes up.
- `code-review` before calling the branch done.
- `implement` to work a ticket end to end.
