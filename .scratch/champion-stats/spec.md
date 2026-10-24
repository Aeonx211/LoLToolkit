# Spec: Champion Stats

**Status:** ready-for-agent

## Problem Statement

I want to get better on one champion (first case: Lillia jungle, as Aeoen#NA1). Public stat sites like lolalytics aggregate millions of strangers' games, so they don't tell me what works *for me*: which matchups I lose, which allies I win with, whether my item, pet, boots and rune choices pay off, and whether I'm out-pacing the enemy jungler. I want lolalytics-style tables built only from my own games, and the ability to drill down by stacking choices until the sample runs out or a pattern shows.

## Solution

A new **Champion Stats** tab in the existing web UI, plus a CLI, backed by a new `champion_stats` tool folder. For a **tracked player** and their **focus champion**, it backfills their ranked games on that champion, extracts one row of facts per game, and shows sections of **cuts**: header summary, Matchups, Allies, Builds, Runes, Camp Pace, Game Length. Every row of every cut is clickable; clicking adds it to the **filter stack**, narrowing the **focus slice** and recalculating every other cut instantly in the browser (ADR 0002). The tables are for observation: they show where results differ, not what to do.

## User Stories

1. As a tracked player, I want to configure a list of (Riot ID, focus champion) pairs, so that the tool can serve more than one player later.
2. As a tracked player, I want Aeoen#NA1 with Lillia to be the first configured pair, so that it works for me out of the box.
3. As a tracked player, I want the first run to backfill up to 100 of my ranked solo games on my focus champion, so that I have a meaningful sample immediately.
4. As a tracked player, I want later runs to fetch only games I haven't stored yet, so that refreshing is fast and doesn't waste API calls.
5. As a tracked player, I want the backfill to stop early and tell me if my history has fewer than 100 qualifying games, so that I know the sample is complete.
6. As a tracked player, I want to see backfill progress (games scanned, games kept) while it runs, so that I know it hasn't stalled.
7. As a tracked player, I want remakes excluded, so that they don't distort win rates.
8. As a tracked player, I want a Solo / Flex / Both queue toggle defaulting to Solo, so that I can compare queues or pool them.
9. As a tracked player, I want a patch-range filter, so that I can ignore games from before a big item or rune change.
10. As a tracked player, I want a header summary of the current focus slice (games, W–L, win %, average KDA, average CS), so that I know the baseline every cut is compared to.
11. As a tracked player, I want every cut row to show games, W–L, win %, pick rate and delta versus the current slice baseline, so that I can tell whether a choice beats my own average.
12. As a tracked player, I want rows sorted by default by a sample-size-aware score (Wilson lower bound of win rate, and of delta), so that a 2–0 doesn't top the list.
13. As a tracked player, I want any column to be sortable, so that I can look at things my own way.
14. As a tracked player, I want rows below 5 games greyed out but still clickable, so that I see thin data without being misled by it.
15. As a tracked player, I want a minimum-games setting I can change, so that I can trade confidence for coverage.
16. As a tracked player, I want win rate by enemy champion in each role (Top, Jungle, Mid, ADC, Support), so that I know which enemy picks I struggle against.
17. As a jungler, I want my matchup (vs the enemy jungler) highlighted as its own cut, so that I see my direct opponent stats first.
18. As a tracked player, I want win rate by ally champion in each role, so that I know which teammates' picks suit me.
19. As a tracked player, I want no roleless ally/enemy cuts, so that every champion stat is tied to the role it was played in.
20. As a tracked player, I want games where Riot didn't record a player's role kept in the totals but left out of that player's role cut, so that bad data doesn't invent roles.
21. As a jungler, I want win rate by jungle pet choice (Gustwalker, Scorchclaw, Mosstomper), so that I know which pet works for me.
22. As a tracked player, I want win rate by completed boots, ignoring the base boots item, so that I can compare boot choices.
23. As a tracked player, I want win rate by completed legendary item in each slot 1–5 (slot = order completed, boots excluded, components ignored), so that I can compare first, second and later item choices.
24. As a tracked player, I want win rate per completed item regardless of slot, so that I see an item's overall record.
25. As a tracked player, I want "most common" and "highest win" 3-item paths shown side by side at the top of Builds, so that I compare habit with results.
26. As a tracked player, I want win rate by keystone, so that I know which keystone works for me.
27. As a tracked player, I want win rate by primary and secondary rune tree, so that I can compare tree pairings.
28. As a tracked player, I want win rate for each individual rune, so that I can judge minor runes too.
29. As a tracked player, I want a full rune page cut that only shows pages used 5+ times, so that I can spot my best whole page without a wall of one-offs.
30. As a tracked player, I want each rune's per-game values (e.g. Electrocute damage) averaged for wins and for losses, so that I can tell whether a rune is doing anything.
31. As a tracked player, I want rune value labels to be a best guess marked "unverified", with raw var1–var3 shown for runes without a label, so that I'm never misled by a confident wrong label.
32. As a tracked player, I want rune values clearly framed as diagnostic, so that I don't read "higher value in wins" as "the rune is better".
33. As a jungler, I want my cumulative jungle monsters killed vs the enemy jungler's at 3, 5, 8 and 10 minutes, so that I see my camp pace.
34. As a jungler, I want win rate when ahead vs behind on camp pace at 5 and 10 minutes, so that I know how much pace matters for me.
35. As a jungler, I want jungle CS before 10 minutes and enemy-jungle camps taken, per game and averaged for wins and losses, so that I see why my pace was high or low.
36. As a jungler, I want which team took first dragon and first herald, and win rate for each, so that I see my early objective control.
37. As a tracked player, I want win rate by game length bucket (<25, 25–30, 30–35, 35+ minutes), so that I see whether I win short or long games.
38. As a tracked player, I want to click any row (enemy or ally champion in a role, matchup, item slot, item, boots, pet, keystone, tree, rune, rune page, camp-pace bucket, first dragon/herald, game length bucket) to add it to the filter stack, so that I can drill down.
39. As a tracked player, I want every other cut to recalculate instantly after each click, so that drilling feels like exploration rather than waiting.
40. As a tracked player, I want a chip row showing the active filter stack, with an x on each chip and "clear all", so that I can see and undo my drill-down.
41. As a tracked player, I want clicking a selected row again to remove it from the stack, so that toggling is natural.
42. As a tracked player, I want a "N games match" banner, so that I always know how thin the current slice is.
43. As a tracked player, I want rows that would leave zero games disabled, so that I can't drill into nothing.
44. As a tracked player, I want the tab to remember my last slice and filter stack in browser storage like the other tabs do, so that reopening the page is instant.
45. As a tracked player, I want a CLI that prints the same cuts for a player and champion, so that I can use it without the browser.
46. As a tracked player, I want item, rune and champion names and icons from Data Dragon, so that the tables are readable.

## Implementation Decisions

- **New tool folder** `champion_stats` alongside Tools 1–3, using the shared data layer. Tools 1–3 are not changed.
- **Tracked players config:** a list of (Riot ID, focus champion) pairs, seeded with Aeoen#NA1 / Lillia. The tab also lets you type a Riot ID and champion.
- **Backfill:** page through the player's match IDs for the selected queue(s), fetch each match (without timeline) to check the champion, and fetch the timeline only for focus-champion games. Stop at 100 kept games or end of history. Stored matches are never refetched. It runs as a job through the existing web UI job system, so progress streams the same way Game Analysis does. Riot's match list can't filter by champion, which is why each candidate match must be fetched.
- **Game row:** the core of the feature, a pure extraction from one stored match + timeline + puuid into one flat record. Fields: match id, patch, queue, start time, duration, win, KDA, CS; ally and enemy champion per role (roles may be missing); jungle pet; completed boots; completed legendary items in completion order (from timeline purchase, sell and undo events, with completion and boots tiers decided from Data Dragon item data); keystone, primary and secondary trees, each selected rune with var1–var3, stat shards; camp pace at 3, 5, 8 and 10 minutes for you and the enemy jungler (cumulative jungle minions from per-minute frames); jungle CS before 10, enemy-jungle monsters killed; first dragon and first herald team; game length bucket. Remakes produce no row.
- **API:** one endpoint returning the game rows for a (player, champion, queue set) plus the Data Dragon names needed to render them. Patch-range, filter stack and every cut are computed in the browser from those rows (ADR 0002).
- **Cut computation (browser):** each cut groups the filtered rows by one key and reports games, wins, win %, pick rate (games with the key / slice games), delta vs slice win %, and a Wilson lower bound used for the default sort. A filter-stack entry is (cut, key); a row matches the stack when it matches every entry. "Would leave zero games" is checked per candidate row by counting matches with that entry added.
- **Rune value labels:** a small hand-maintained table mapping rune id to labels for var1–var3, starting as best guesses and flagged unverified. Unlabeled runes show raw values.
- **Tab:** a single Champion Stats tab. Layout top to bottom: slice controls (player, champion, queue toggle, patch range, min games) → filter chips + "N games match" → header summary → Matchups → Allies → Builds (most common / highest win paths, slots 1–5, all items, boots, pet) → Runes (keystone, trees, individual runes, pages, rune values) → Camp Pace (pace table, ahead/behind, objectives) → Game Length.
- **Glossary terms used:** tracked player, focus champion, focus slice, role, matchup, cut, filter stack, rune value, camp pace (see GLOSSARY.md).

## Testing Decisions

- Good tests check external behaviour: given a synthetic match and timeline, the extracted game row has the right facts. They don't assert on internals.
- **Primary seam: game-row extraction.** It is pure Python and carries almost all the logic and edge cases: item completion order with sells and undos, boots tier, pet detection, roles missing, rune values, camp pace at minute marks, first objectives, remakes. Tested with the existing synthetic match/timeline builders, extended for items, perks and jungle minions. Prior art: the fixture-based tests for the analysis engine and data layer.
- **Backfill** is tested against a fake client, like the existing data-layer tests: it stops at the target count, skips non-focus champions without fetching their timelines, and never refetches stored matches.
- **Browser cut computation** has no JS test framework in the repo and none is added. It is kept small and checked by driving the tab with the pre-installed Playwright against fixture rows during development.
- Run the suite with `python -m unittest discover -t . -s tests`.

## Out of Scope

- Exact per-camp clear times (the timeline has no per-camp events). Revisit if a data source appears.
- Summoner spells, skill order and starting-item cuts (declined).
- A "Takeaways" block of generated advice.
- Roleless ally and enemy cuts.
- Players other than the tracked player's own games (no global or rank-wide averages).
- Changes to Tools 1–3.

## Further Notes

- The cloud environment currently blocks `api.riotgames.com`, `ddragon.leagueoflegends.com` and `lolalytics.com`. The user is allowing them and adding a Riot API key as an environment secret. Until then, everything except the real backfill and rune-label verification can be built against fixtures.
- Rune-value labels are verified against the backfilled 100 games in their own ticket, after the backfill works.
- Reference: lolalytics champion build pages (win rate delta, pick rate, most common vs highest win builds).
