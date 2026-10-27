# 04: Pilot run on the PC (30 minutes)

**Status:** ready-for-human

**Blocked by:** 03, and a fresh Riot dev key (they expire every 24 hours)

**What to do:** On the PC, with nothing else using the key (the rate limiter is per process):

1. `python -m champion_stats.population Lillia --since <previous patch start> --hours 0.5`
2. Note the numbers it prints: requests spent on discovery vs matches, Lillia games kept, games per hour.
3. Decide from that whether a few-hour run gives enough games (target: 1,500+). If discovery eats most of the budget,
   see the Comments for fallbacks before the long run.

- [ ] Pilot numbers recorded in Comments
- [ ] Go / adjust decision recorded

## Comments

- Fallbacks if yield is low: start Emerald from Emerald I only; or require Lillia in the player's top-3 mastery
  (fewer, heavier players); or run several nights (discovery is saved, so later runs mostly crawl games).
