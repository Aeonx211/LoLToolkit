# 02: Discover focus-champion players on the ladder

**Status:** ready-for-agent

**Blocked by:** 01

**What to build:** `champion_stats/population.py`: walk the ladder top-down (Challenger → Emerald IV), mastery-check
each player for the focus champion, and keep those whose `lastPlayTime` is at or after `since` (the previous patch's
start, passed in as a date). Save each checked player in the store (checked or not, kept or not, with tier and mastery
points) so a rerun never re-checks them.

- [ ] Candidates are ordered by mastery points, highest first
- [ ] Respects a request budget and stops cleanly when it runs out; a rerun continues where it stopped
- [ ] Progress output: players checked, candidates found, requests used
- [ ] Tested with a fake client (no network)

## Comments

- Ladder order matters for the pilot: start high elo so Master+ is fully covered before Emerald pages, which are huge.
