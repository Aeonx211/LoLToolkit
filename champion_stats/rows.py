"""One flat record of facts per game, from the tracked player's point of view. The browser computes every cut and
the filter stack from these rows (ADR 0002), so anything a cut needs must be extracted here."""

from causal_analysis.archetypes import DEFAULT_THRESHOLDS

ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def is_remake(match):
    info = match["info"]
    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:
        duration //= 1000  # older payloads report milliseconds
    return duration < DEFAULT_THRESHOLDS.remake_s or any(
        p.get("gameEndedInEarlySurrender") for p in info["participants"])


def _patch(game_version):
    return ".".join((game_version or "").split(".")[:2])


def game_row(match, timeline, puuid):
    """The game's facts for `puuid`, or None for a remake or a game they weren't in."""
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
    return {
        "match_id": match["metadata"]["matchId"],
        "patch": _patch(info.get("gameVersion")),
        "queue": info.get("queueId"),
        "start": info.get("gameStartTimestamp") or info.get("gameCreation"),
        "duration_s": duration,
        "win": bool(me.get("win")),
        "champion": me["championName"],
        "role": me.get("teamPosition") or "",
        "kills": me.get("kills", 0),
        "deaths": me.get("deaths", 0),
        "assists": me.get("assists", 0),
        "cs": me.get("totalMinionsKilled", 0) + me.get("neutralMinionsKilled", 0),
        "allies": allies,
        "enemies": enemies,
    }
