# 05: Camp pace and objectives

**What to build:** The Camp Pace section: the tracked player's cumulative jungle monsters killed vs the enemy jungler's at 3, 5, 8 and 10 minutes, win rate when ahead vs behind at 5 and 10 minutes, jungle CS before 10, enemy-jungle camps taken, and which team took first dragon and first herald. Ahead/behind and first-objective rows are clickable into the filter stack.

**Blocked by:** 01

**Status:** done

- [x] Camp pace at each mark comes from per-minute frames; jungle CS before 10 and enemy-jungle kills from end-of-game stats (tested)
- [x] First dragon and first herald team from the timeline's elite monster kills (tested)
- [x] Averages shown separately for wins and losses

## Comments

- Done. Pace compares against the enemy in your role, which for a jungler is the enemy jungler. Enemy-jungle camps come from `totalEnemyJungleMinionsKilled`, falling back to the challenges field. Neither has been checked against a real payload yet (ticket 08).
