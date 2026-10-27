# 05: Population view in the tab and the phone export

**Status:** ready-for-agent

**Blocked by:** 03

**What to build:** The Champion Stats tab and `champion_stats.export` can load population rows (from `data/`) as well as
the tracked player's rows, with a **Me / Population** toggle. Every cut and the filter stack work the same on either
(ADR 0002: the browser computes cuts from rows).

- [ ] Toggle switches the row set; the filter stack and patch range carry over
- [ ] Cut tables get a **Players** column (distinct `player` hashes) in Population view
- [ ] Optional per-player cap (count at most N games per player) so one-tricks don't dominate
- [ ] Tier filter (Emerald / Diamond / Master+) in Population view
- [ ] In **Me** view, an option to measure Δ against the population's win rate for the same cut row under the same
      filter stack (rows with too few population games show no Δ)
- [ ] Export still runs on Chrome 80 (see the Champion Stats handoff's compatibility notes) and stays usable on a
      phone; trim unused row fields if the page passes ~5 MB
- [ ] Export writes to a gitignored path (population data isn't committed)

## Comments

- "Item X as the Nth item" already exists: Builds shows completed legendaries by slot 1–5, and each row is clickable
  into the filter stack, so stacking "2nd item = X" with other filters needs no new cut.
