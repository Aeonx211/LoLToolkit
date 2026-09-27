LoL Insight Toolkit — Project Spec
Sep 27, 2026 · @Jake Saladino 
A single repo housing three League of Legends tools that go beyond raw stat tracking: a post-game engine that explains why a game was won or lost, a live-game advisor that uses that engine's logic in real time, and a build theorycrafting simulator.
Overview
The repo holds three tools that share one Riot API ingestion/storage layer instead of each tool hitting the API on its own. Suggested layout: /data-layer (shared ingestion + storage), /causal-analysis (Tool 1), /live-advisor (Tool 2), /build-sim (Tool 3).
Tool 2 also reads Tool 1's win/loss verdicts live: when Tool 1 tags a player as the team's carry, Tool 2 surfaces that player as the priority focus target mid-game.
Tool 1 — Post-Game Causal Analysis Engine
The core differentiator. Instead of "more gold = better," this tool answers: why did this specific game end the way it did?
Narrative classification
Run each finished match through a rules/heuristics pipeline (later: a lightweight model) that tags the game with one or more of these win/loss archetypes:
Archetype
Signal
Stomp
One team held a large gold/XP lead from an early timestamp to the end, with no significant lead swing
Comeback
Team was down by a large gold/XP margin at a snapshot (e.g. 15 min) and still won
Thrown
Team held a lead above a threshold (e.g. +3k gold, +2 kills) at some point, then lost it and the game
Snowballed-on
Team was ahead, then one enemy player's stat curve (kills/gold/damage share) spiked sharply and correlates with the lead reversing
Carried
One player's share of team kills, damage, or gold vastly exceeds their role's typical share for that game length
Even-then-decided
Game stayed close (lead within a small band) until a late decisive fight/objective
Data model per match
• Timeline snapshots (gold, XP, kills, objectives) at fixed intervals (e.g. every 60s) per team and per player
• Lead-swing detection: largest gold/XP lead held by each team and the timestamp it peaked, plus the timestamp (if any) the lead flipped
• Per-player "impact share" over time: rolling share of team kills + damage + gold, so a spike is visible
• Key-moment extraction: objectives (dragon/baron/herald/towers) tagged with the gold/XP swing they produced, so "the game turned here" moments are identifiable
Output
For a given match: a short natural-language verdict ("Winning by 4k at 15:00, threw the lead after a bad baron fight at 22:30") plus the underlying timeline data to support it, and a tag for which archetype(s) applied.
Why this matters for the other two tools
This engine's per-player "impact share" and per-champion outcome data is the input Tool 2 uses to flag likely carries and predict opponent behavior, and it's the ground truth Tool 3's simulations should validate against (e.g. "does the simulated build actually track with what wins these games?").
Tool 2 — Live Game Advisor
A real-time overlay/companion for the game you're currently in, built on top of Tool 1's analysis of the ten players' match histories.
Core: carry-target flagging
Before or early in the game, pull each player's recent match history through Tool 1's engine and surface: "this player has been tagged 'carried' in X% of their recent wins — track them." This turns a vague sense of "who's the threat" into a number grounded in actual past outcomes, not just current KDA.
Counter-itemization (core)
For the enemy team's picks, surface:
• Aggregate healing/lifesteal/omnivamp on the enemy team — flags when a Grievous Wounds item should be prioritized, and how early
• Aggregate magic vs. physical damage split — informs MR vs. armor priority
• Which enemy champions have historically weak early game vs. strong late (or vice versa) — informs tempo of item spikes to build toward
Opponent build prediction (stretch goal)
For each enemy player, pull their match history for their current champion and compute:
• Modal (most common) full build, and how consistent it is (e.g. "builds Rabadon's 85% of games on this champion")
• Typical build order / power spike timings
• A confidence score, so "this player will build X" claims are qualified by how predictable that player actually is
This directly extends Tool 1's data model — it's the same per-player match history, just queried per-champion instead of per-game.
Live data needed
• Live client/spectator data: champion select, summoner spells, current items, gold, level
• Historical match data per player (via the shared data layer) to compute the carry-likelihood and build-prediction stats above
Tool 3 — Build Theorycrafting Simulator
Given a champion, a rune page, an item set, and an ability-rank/rotation order, simulate an idealized combat sequence and project outcomes — answering "if I built this instead, what would actually happen?"
Inputs
• Champion + level
• Rune page (keystone + full tree)
• Item build (in build order, so mid-fight state at partial builds can be simulated too)
• Ability rotation/rank order
• Target scenario: a dummy target, or a defined enemy (champion + their assumed build/resistances, ideally pulled from Tool 2's opponent-build predictions)
Simulation outputs
• Projected damage done over a fixed window (e.g. a full combo, or a X-second trade)
• Projected effective healing/shielding over that same window
• Projected damage taken in a symmetric trade (if the target is also given a rotation)
• Breakpoints: how the outputs change if one item or rune is swapped, so you can A/B two builds directly
Engine approach
This needs an actual combat math model: base stats + growth per level, item stat totals, ability ratios (AD/AP scaling) per rank, damage formulas (armor/MR mitigation, penetration types, true damage), and on-hit/proc effects (e.g. spellblade, on-hit item procs) applied in rotation order. This is the most build-heavy of the three tools because League's combat math has a lot of edge cases (execute thresholds, shields absorbing before or after mitigation, etc.) — realistic scope for v1 is a subset of champions/items rather than full coverage.
Tie-in to Tool 1
Once this simulator exists, its projected outcomes can be checked against Tool 1's real match data for the same champion/build combos — a sanity check on whether the simulated "good build" actually correlates with real wins.
Shared Data Layer
All three tools need Riot's API and should hit it through one shared module rather than three separate integrations.
Riot API endpoints needed
Endpoint
Used by
Purpose
Account-V1 (by-riot-id → puuid)
All tools
Resolve a Riot ID (e.g. Aeoen#NA1) to the puuid every other endpoint keys off of — needed once at lookup time, then cached
Match-V5 (match detail + timeline)
Tool 1
Full timeline snapshots for causal analysis
Match-V5 (match list by puuid)
Tool 1, Tool 2
Recent match history per player
Spectator-V5 (active game)
Tool 2
Current game roster, champs, spells
League-V4 / Summoner-V4
Tool 2
Rank context for the current game
Champion Mastery-V4
Tool 2 (stretch)
Per-champion mastery as a secondary signal for how practiced a player is on their pick, alongside carry-tag rate
Champion/Item static data (Data Dragon)
Tool 2, Tool 3
Champion base stats, item stats, ability data

API key rate limits (dev key, per Riot dashboard)
• App-wide: 20 requests / 1 second, 100 requests / 2 minutes — this is the hard ceiling the shared queue layer must throttle to, well below any single method's own per-method limit
• Match-V5 (all methods): 2000 req/10s — effectively unconstrained by the app-wide cap above
• Spectator-V5: 3000 req/10s, 180000 req/10min
• League-V4 entries by-puuid, Account-V1, Champion Mastery-V4, lol-challenges-v1: 20000 req/10s, 1.2M req/10min
• League-V4 challenger/master/grandmaster leagues: 30 req/10s, 500 req/10min
• Summoner-V4 by-puuid: 1600 req/min
Since the app-wide 20/1s and 100/2min limits are far tighter than any individual method's quota, the rate-limit-aware queue in the shared data layer should throttle against the app-wide limits, not the per-method ones.
Storage
• A match store keyed by match ID, holding raw timeline + Tool 1's derived archetype tags and impact-share data, so Tool 2 never has to recompute Tool 1's analysis for a player it's already processed
• A per-player rollup (win rate, carry-tag rate, per-champion modal builds) refreshed incrementally as new matches are pulled, rather than recomputed from scratch each lookup
• Respect for Riot API rate limits: a queue/cache layer so Tool 2's live lookups (which need to be fast) aren't blocked behind Tool 1's bulk historical pulls
Suggested Build Order
1. Shared data layer — Riot API client, rate-limit-aware queue, match/player storage. Nothing else works without this.
2. Tool 1 (Post-Game Causal Analysis) — the highest-value and most novel piece; also the one Tool 2 and Tool 3 both lean on.
3. Tool 2 core (Live Advisor) — live spectator data + carry-target flagging and counter-itemization, using Tool 1's per-player data.
4. Tool 2 stretch (opponent build prediction) — add once core is solid.
5. Tool 3 (Build Simulator) — independent combat-math work; can start in parallel with Tool 2 once the shared data layer's static champion/item data is in place, since Tool 3 doesn't strictly need live match data to begin...................................................