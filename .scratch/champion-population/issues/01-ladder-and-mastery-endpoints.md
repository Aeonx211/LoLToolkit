# 01: Ladder and mastery endpoints in the data layer

**Status:** ready-for-agent

**Blocked by:** none

**What to build:** `RiotClient` methods (platform host, BULK priority by default) for:

- `/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5`, `grandmasterleagues/...`, `masterleagues/...`
- `/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page=N` (Diamond and Emerald, divisions I–IV; an empty page ends the tier)
- `/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/by-champion/{championId}` (404 means never played: return None)

Check the real responses carry `puuid` (league entries switched from summonerId to puuid; confirm on the PC run and
note it here).

- [ ] Methods added next to the existing ones in `data_layer/client.py`, same style
- [ ] Tests with a fake transport: paths, params, paging stops on an empty page, mastery 404 returns None

## Comments
