# 08: Real backfill and rune label check (run on your PC)

**What to build:** Backfill 100 Lillia ranked solo games for Aeoen#NA1 against the real Riot API, check the tab works on real data, and correct the rune-value labels from real values.

**Blocked by:** 04, and a Riot API key. The cloud environment can't reach the Riot API, so this runs on your PC.

**Status:** done

## Steps on your PC

1. Get a fresh key from https://developer.riotgames.com/ (dev keys expire after 24 hours).
2. In the repo folder, pull the branch: `git pull origin claude/lillia-jungle-stats-tracker-psjoh1`
3. Put the key in `.env` as `RIOT_API_KEY=...` (copy `.env.example` if `.env` doesn't exist).
4. Start the UI: `python -m webui --open`, go to Champion Stats, enter `Aeoen#NA1` and `Lillia`, click Load. The first backfill takes a few minutes on a dev key.
5. Check the tables look right against what you remember (pet, boots, first item, keystone).
6. Export the real rune values for checking: `python -m champion_stats.dump_runes "Aeoen#NA1" Lillia > rune_values.json` (added in ticket 04), then start a Claude session and ask it to verify the rune labels in `champion_stats` against that file.
7. Don't commit `rune_values.json` or anything under `data/` (or your `.env`).

- [x] 100 games (or full history) backfilled: full history, 61 Lillia solo games out of 838 ranked solo games scanned
- [x] Tab checked on real data: every section renders, no console errors
- [x] Rune labels corrected and the "unverified" mark removed for checked ones (Triumph, Cash Back, Gathering Storm)

## Comments

- 2026-10-23, run on the user's PC against the real Riot API. `rows.py` was checked against real match and timeline
  payloads (patches 16.16–16.21) and the item data from Data Dragon 16.20.1.
- **Bug fixed: boots.** Every tier-2 boot now lists its tier-3 upgrade under `into`, so the old rule (Boots tag and
  no `into`) rejected them: real rows had no boots unless a tier-3 was bought. Completed boots are now Boots-tagged
  items built *from* something (tier 2 and 3), plus upgrades of completed boots, because Gunmetal Greaves ships
  without the Boots tag. Completed boots are never counted as legendaries. Tier-3 upgrades show up as ITEM_PURCHASED,
  so the last completed boots (tier 3 when bought) is what the row reports. Tested.
- **Bug fixed: enemy jungle.** `totalEnemyJungleMinionsKilled` is in the same CS units as frame `jungleMinionsKilled`
  (e.g. 26). The fallback, `challenges.enemyJungleMonsterKills`, counts something smaller (20 in the same game), so
  it's gone. The UI line said "camps", which neither field is, so it now reads "Enemy jungle CS taken". Tested.
- **Checked and correct as built:** ITEM_PURCHASED, ITEM_UNDO (`beforeId` item / `afterId` 0 undoes a purchase;
  `beforeId` 0 / `afterId` item undoes a sale) and ITEM_SOLD shapes; the "no `into` and ≥ 2000 gold" legendary rule
  (no false positives or misses across every item bought; Cash Back paid exactly 7.5% of the legendaries it found in 25/25
  games); the Oracle Lens swap and pet buys (1101–1103) are logged as purchases and stay out of items; perks layout
  and var1–var3; `jungleMinionsKilled` in participant frames (minute 10 equals `jungleCsBefore10Minutes`, which is
  a float such as 82.0000001 or 63.75); `monsterType` `DRAGON` (elder is `DRAGON` + `ELDER_DRAGON`) and
  `RIFTHERALD` (void grubs are `HORDE`, plus `ATAKHAN` and `BARON_NASHOR`); remakes (65–142 s, all with
  `gameEndedInEarlySurrender`). Tests now use item data shaped like real Data Dragon.
- **Rune labels.** Per-rune verification: `VERIFIED_RUNES` in `rune_labels.py`, sent as `names.rune_labels_verified`;
  the UI puts an "unverified" chip on each unverified rune's rows instead of one chip on the section. Verified from
  exact relationships in every game: Triumph (var2 = 20 × takedowns), Cash Back (var1 = 7.5% of completed
  legendaries' gold), Gathering Storm (var1 = 8 × T(whole 10-minute blocks)). Conqueror, Coup de Grace, Legend:
  Haste, Celerity, Approach Velocity, Axiom Arcanist, Conditioning, Unflinching and the rarely used ones stay
  unverified: their sizes are plausible but nothing in the payload pins them down. Labelled runes used to hide slots
  that had no label even when real games filled them (Legend: Haste var2, Axiom Arcanist var2, Conditioning var2 and
  var3, Waterwalking var2); those now show as raw `varN`. Deathfire Touch (8992) is new and has no label.
- **Open, not changed (design questions for the user):** camp pace compares against the enemy in your role (ticket
  05), while the spec and glossary say the enemy jungler; it only differs in off-role games, and all 61 real games are
  jungle. The 300 s remake cutoff also catches 4–5 minute *normal* surrenders (`gameEndedInSurrender`, seen in 2
  other players' games, none of the user's).
- **Code-review follow-ups (not fixed):** champion input isn't normalised to Riot's internal names (e.g. "Wukong" is
  `MonkeyKing`); the backfill has no cap on games scanned (838 games took about 25 minutes on a dev key); new
  focus games fetch the match twice; items use the latest Data Dragon for every patch; `is_remake` ignores the Tuning
  tab's remake cutoff; `csCuts()` is rebuilt per row in the browser filter; timeline events are sorted three times
  per game.
- Dev note: don't run long read queries on `data/toolkit.db` while a backfill writes to it. Holding a read lock past
  SQLite's timeout made the first run fail with "database is locked".
