# LoL Insight Toolkit

Three League of Legends tools on one shared Riot API layer. See [Spec.md](Spec.md) for the full design.

| Folder | What it does |
|---|---|
| `data_layer/` | Rate-limited Riot API client, SQLite match/player store, Data Dragon static data |
| `causal_analysis/` (Tool 1) | Tags each game (Stomp, Comeback, Thrown, Snowballed-on, Carried, Even-then-decided) and explains why it was won or lost |
| `live_advisor/` (Tool 2) | Focus target from Tool 1 carry tags, counter-itemization, and opponent build prediction for your current game |
| `build_sim/` (Tool 3) | Combat simulator for combos and trades, with A/B build comparison and item/keystone breakpoints |

## Setup

Requires Python 3.11+. There are no third-party dependencies.

```
cp .env.example .env    # then put your key in RIOT_API_KEY
```

Optional `.env` settings: `RIOT_PLATFORM` (default `na1`) and `TOOLKIT_DATA_DIR` (default `./data`, which is gitignored).

## Web UI

```
python -m webui --open        # http://127.0.0.1:8765
```

The UI has one tab per tool plus a **Tuning** tab:
- **Game Analysis:** recent games with perspective tags such as "We threw" or "You carried". Click a game for its gold chart, key moments and players.
- **Live Advisor:** run it during a game, or use "Replay advisor" on any past game.
- **Build Sim:** build editor, simulate, find breakpoints, and A/B compare against a second build.
- **Tuning:** edit every threshold and hand-entered number. Saved values go to `tuning.json`, which the CLIs also read. Delete that file or use "Reset all" to go back to the defaults.

The server only listens on localhost and rejects requests addressed to any other hostname.

## CLI usage

```
# Tool 1: why games were won or lost
python -m causal_analysis player "Aeoen#NA1" -n 20            # recent games (remakes skipped)
python -m causal_analysis player "Aeoen#NA1" -q 420 --json    # ranked solo only, full JSON
python -m causal_analysis match NA1_5649679454                # one game: leads, key moments, per-player impact

# Tool 2: live advisor (run it while you're in a game)
python -m live_advisor "Aeoen#NA1"
python -m live_advisor "Aeoen#NA1" --allies --depth 10
python -m live_advisor "Aeoen#NA1" --replay NA1_5649679454    # try it on a past game (only uses earlier history)

# Tool 3: build simulator
python -m build_sim run build_sim/builds/velkoz_vs_garen.json --log
python -m build_sim compare build_sim/builds/velkoz_vs_garen.json build_sim/builds/velkoz_void_staff.json
python -m build_sim breakpoints build_sim/builds/velkoz_vs_garen.json
```

Matches and analyses are cached in `data/toolkit.db`. Re-running a player costs one API call (the match list), and Tool 2 reuses everything Tool 1 has already stored.

### Scenario files (Tool 3)

A scenario has an `attacker`, a `target`, and an optional `window` in seconds. The target is either another champion build or `{"dummy": {"hp": 2500, "armor": 60, "mr": 50}}`. A build has:
- `champion` and `level`
- either `skill_order` (for example `"QEW"`) or explicit `ranks`
- `items`
- `runes`: a `keystone`, `minor` runes and `shards`
- `rotation`: a list of `Q`, `W`, `E`, `R` and `AA`

If both sides have rotations, they run at the same time, so you get a symmetric trade.

- **v1 champions:** Vel'Koz, Lillia, Karthus, Garen, Vayne (in `build_sim/kits.py`).
- **Data sources:**
  - Base stats and item stats come from Data Dragon (current patch).
  - Ability numbers come from Meraki.
  - Item passives and runes are hand-entered from Meraki and CommunityDragon (in `build_sim/effects.py`).
- **Unmodeled items:** items with passives that aren't modeled still count for their stats, and the output lists them.
- **Keystones:** Electrocute, Arcane Comet, Press the Attack, Conqueror, Dark Harvest.
- **Minor runes:** Coup de Grace, Cut Down, Last Stand, Absolute Focus.

## Tests

```
python -m unittest discover -s tests -t .
```

## Notes

- **Rate limits:** the client throttles to the key's app-wide limits (20/1s and 100/2min, tracked per routing host). Bulk pulls stop at 80% of each window, which leaves headroom for live lookups.
- **Tuning:** stored Tool 1 results are cached under a hash of the tuning values, so tuning changes re-analyze stored games automatically. If you change Tool 1's code, bump `ANALYSIS_VERSION` in `causal_analysis/engine.py` so cached results are recomputed. Player rollups adjust themselves without double counting.

## Open TODOs

These are also marked `TODO` in the code.

- **Tool 1:**
  - Calibrate the archetype thresholds (`causal_analysis/archetypes.py`) against a larger sample.
  - The turning-point heuristic works from 60s timeline frames.
  - Carry baselines are per role; per-champion baselines would stop damage supports like Vel'Koz from inflating.
- **Tool 2:**
  - Calibrate the carry-flag and counter-itemization cutoffs.
  - Champion-specific stats only see games already in the store.
  - The tempo signal (early vs late) is a rough proxy.
- **Tool 3:**
  - Re-verify item passive and rune numbers each patch.
  - Not modeled yet: BotRK's %-current-HP value, Arcane Comet range scaling, shield durations, Vel'Koz R applying Deconstruction stacks, Karthus's passive, Garen E crits, and Lich Bane's attack-speed boost.
- **Data layer:** the rate limiter is per process, so running two tools at once can exceed the key's limit together.
