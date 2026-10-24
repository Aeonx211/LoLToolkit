# 08: Real backfill and rune label check (run on your PC)

**What to build:** Backfill 100 Lillia ranked solo games for Aeoen#NA1 against the real Riot API, check the tab works on real data, and correct the rune-value labels from real values.

**Blocked by:** 04, and a Riot API key. The cloud environment can't reach the Riot API, so this runs on your PC.

**Status:** ready-for-human

## Steps on your PC

1. Get a fresh key from https://developer.riotgames.com/ (dev keys expire after 24 hours).
2. In the repo folder, pull the branch: `git pull origin claude/lillia-jungle-stats-tracker-psjoh1`
3. Put the key in `.env` as `RIOT_API_KEY=...` (copy `.env.example` if `.env` doesn't exist).
4. Start the UI: `python -m webui --open`, go to Champion Stats, enter `Aeoen#NA1` and `Lillia`, click Load. The first backfill takes a few minutes on a dev key.
5. Check the tables look right against what you remember (pet, boots, first item, keystone).
6. Export the real rune values for checking: `python -m champion_stats.dump_runes "Aeoen#NA1" Lillia > rune_values.json` (added in ticket 04), then start a Claude session and ask it to verify the rune labels in `champion_stats` against that file.
7. Commit `rune_values.json` (or paste it to Claude), not your `.env`.

- [ ] 100 games (or full history) backfilled
- [ ] Tab checked on real data
- [ ] Rune labels corrected and the "unverified" mark removed for checked ones
