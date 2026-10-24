# LoL Insight Toolkit

Personal League of Legends analysis tools built on one shared Riot API layer. Terms are added here as they are resolved in design sessions.

## Language

**Tracked player**:
A player (identified by Riot ID) whose match history the toolkit ingests and analyzes, as opposed to the other nine players in each match.
_Avoid_: User, summoner

**Focus champion**:
The one champion a tracked player is being improved on. Stats only count games where the tracked player played it. Tracked players are configured as a list of `(Riot ID, focus champion)` pairs.
_Avoid_: Main, pick

**Focus slice**:
The set of games a stats view covers: one tracked player, their focus champion, one queue choice (ranked solo, ranked flex, or both; default solo), and an optional patch range.
_Avoid_: Dataset, filter

**Role**:
One of the five team positions (Top, Jungle, Mid, ADC, Support). Every ally and enemy stat is keyed by champion *and* role; there is no roleless cut.
_Avoid_: Lane, position (the API field name only)

**Matchup**:
The tracked player's focus champion against the enemy in the same role. For a jungler this is the enemy jungler.
_Avoid_: Counter

**Cut**:
One breakdown of win rate by a single dimension, e.g. by enemy mid champion, by boots, or by keystone. Every cut reports games, W–L, and win %, and is greyed out below a minimum sample.
_Avoid_: Stat, table

**Filter stack**:
The ordered list of selections the user has made on the Champion Stats tab (e.g. first item = Riftmaker, then boots = Berserker's). Each selection narrows the focus slice to matching games and every cut recalculates. Replaces precomputed set combinations.
_Avoid_: Combination, set, build

**Rune value**:
The per-game numbers (`var1`–`var3`) Riot attaches to a selected rune, such as damage dealt or stacks. Meaning is rune-specific and kept in a hand-maintained label table. A diagnostic, not a recommendation.
_Avoid_: Rune stats

**Camp pace**:
The tracked jungler's cumulative jungle monsters killed over time, compared against the enemy jungler's at the same game minute.
_Avoid_: Clear time
