"""One flat record of facts per game, from the tracked player's point of view. The browser computes every cut and
the filter stack from these rows (ADR 0002), so anything a cut needs must be extracted here."""

from causal_analysis.archetypes import DEFAULT_THRESHOLDS

ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
PETS = {1101: "Scorchclaw Pup", 1102: "Gustwalker Hatchling", 1103: "Mosstomper Seedling"}
LEGENDARY_MIN_GOLD = 2000  # finished items with no upgrade path that cost less are starters, quest items, etc.
PACE_MARKS = (3, 5, 8, 10)  # minutes
LENGTH_BUCKETS = ((25 * 60, "<25"), (30 * 60, "25–30"), (35 * 60, "30–35"))


def is_remake(match):
    info = match["info"]
    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:
        duration //= 1000  # older payloads report milliseconds
    return duration < DEFAULT_THRESHOLDS.remake_s or any(
        p.get("gameEndedInEarlySurrender") for p in info["participants"])


def _patch(game_version):
    return ".".join((game_version or "").split(".")[:2])


def _length_bucket(duration_s):
    return next((label for limit, label in LENGTH_BUCKETS if duration_s < limit), "35+")


def _events(timeline):
    events = [e for f in timeline["info"]["frames"] for e in f.get("events", [])]
    return sorted(events, key=lambda e: e.get("timestamp", 0))


def _purchases(timeline, participant_id):
    """Item ids the participant bought, in order, with undone purchases removed. Sold items stay: a sold item still
    held its build slot."""
    bought = []
    for e in _events(timeline):
        if e.get("participantId") != participant_id:
            continue
        if e["type"] == "ITEM_PURCHASED":
            bought.append(e["itemId"])
        elif e["type"] == "ITEM_UNDO" and e.get("beforeId") in bought:
            del bought[len(bought) - 1 - bought[::-1].index(e["beforeId"])]
    return bought


def _is_legendary(item):
    tags = item.get("tags", [])
    return ("Boots" not in tags and "Consumable" not in tags and not item.get("into")
            and item.get("gold", {}).get("total", 0) >= LEGENDARY_MIN_GOLD)


def _is_completed_boots(item):
    return "Boots" in item.get("tags", []) and not item.get("into")


def _build(timeline, participant_id, items):
    """(completed legendaries in completion order, last completed boots, jungle pet). Item classification needs Data
    Dragon item data; without it only the pet is known."""
    bought = _purchases(timeline, participant_id)
    pet = next((i for i in bought if i in PETS), None)
    if not items:
        return [], None, pet
    data = [(i, items.get(str(i))) for i in bought if i not in PETS]
    legendaries = [i for i, d in data if d and _is_legendary(d)]
    boots = [i for i, d in data if d and _is_completed_boots(d)]
    return list(dict.fromkeys(legendaries)), (boots[-1] if boots else None), pet


def _runes(me):
    styles = {s.get("description"): s for s in me.get("perks", {}).get("styles", [])}
    primary, sub = styles.get("primaryStyle"), styles.get("subStyle")
    selections = [sel for s in (primary, sub) if s for sel in s.get("selections", [])]
    stat = me.get("perks", {}).get("statPerks", {})
    shards = [stat[k] for k in ("offense", "flex", "defense") if k in stat]
    runes = [sel["perk"] for sel in selections]
    return {
        "keystone": runes[0] if primary and runes else None,
        "primary_tree": primary["style"] if primary else None,
        "secondary_tree": sub["style"] if sub else None,
        "runes": runes,
        "shards": shards,
        "page": "-".join(map(str, runes + shards)) if runes else None,
        "rune_values": {str(sel["perk"]): [sel.get(f"var{i}", 0) for i in (1, 2, 3)] for sel in selections},
    }


def _camp_pace(timeline, my_pid, enemy_pid):
    """{minute: [my cumulative jungle monsters, enemy jungler's]} at each mark the game reached."""
    frames = timeline["info"]["frames"]
    pace = {}
    for minute in PACE_MARKS:
        if minute >= len(frames) or enemy_pid is None:
            continue
        pf = frames[minute]["participantFrames"]
        pace[str(minute)] = [pf[str(my_pid)].get("jungleMinionsKilled", 0),
                             pf[str(enemy_pid)].get("jungleMinionsKilled", 0)]
    return pace


def _first_objective(timeline, monster, my_team):
    e = next((e for e in _events(timeline) if e["type"] == "ELITE_MONSTER_KILL" and e.get("monsterType") == monster),
             None)
    if e is None:
        return None
    return "us" if e.get("killerTeamId") == my_team else "them"


def game_row(match, timeline, puuid, items=None):
    """The game's facts for `puuid`, or None for a remake or a game they weren't in. `items` is Data Dragon's item
    data (id string -> item); without it the build fields stay empty."""
    info = match["info"]
    me = next((p for p in info["participants"] if p["puuid"] == puuid), None)
    if me is None or is_remake(match):
        return None
    allies, enemies = {}, {}
    for p in info["participants"]:
        role = p.get("teamPosition") or ""
        if p is me or role not in ROLES:
            continue
        (allies if p["teamId"] == me["teamId"] else enemies)[role] = p["championName"]
    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:
        duration //= 1000
    role = me.get("teamPosition") or ""
    lane_opponent = next((p["participantId"] for p in info["participants"]
                          if p["teamId"] != me["teamId"] and role and p.get("teamPosition") == role), None)
    items_built, boots, pet = _build(timeline, me["participantId"], items)
    challenges = me.get("challenges", {})
    return {
        "match_id": match["metadata"]["matchId"],
        "patch": _patch(info.get("gameVersion")),
        "queue": info.get("queueId"),
        "start": info.get("gameStartTimestamp") or info.get("gameCreation"),
        "duration_s": duration,
        "win": bool(me.get("win")),
        "champion": me["championName"],
        "role": role,
        "kills": me.get("kills", 0),
        "deaths": me.get("deaths", 0),
        "assists": me.get("assists", 0),
        "cs": me.get("totalMinionsKilled", 0) + me.get("neutralMinionsKilled", 0),
        "allies": allies,
        "enemies": enemies,
        "length": _length_bucket(duration),
        "items": items_built,
        "boots": boots,
        "pet": pet,
        **_runes(me),
        "pace": _camp_pace(timeline, me["participantId"], lane_opponent),
        "jungle_cs_10": round(challenges.get("jungleCsBefore10Minutes", 0)),
        "enemy_jungle_kills": me.get("totalEnemyJungleMinionsKilled", challenges.get("enemyJungleMonsterKills", 0)),
        "first_dragon": _first_objective(timeline, "DRAGON", me["teamId"]),
        "first_herald": _first_objective(timeline, "RIFTHERALD", me["teamId"]),
    }
