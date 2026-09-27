from bisect import bisect_left
from statistics import mean

from causal_analysis.metrics import frame_at_or_before
from causal_analysis.parse import UnsupportedMatch, parse_match
from data_layer import DataLayer

from .history import PlayerHistory

# TODO: first-guess cutoffs for the counter-itemization calls below; tune against stored games.
HEALER_PERCENTILE = 0.80
HEAVY_HEALER_PERCENTILE = 0.90
RESIST_SPLIT = 0.60
EARLY_LANE_GOLD = 400
SCALING_SHARE_GAIN = 0.02
MAX_GAMES = 15


def _participant(match, puuid):
    return next((p for p in match["info"]["participants"] if p["puuid"] == puuid), None)


def _minutes(match):
    info = match["info"]
    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:
        duration /= 1000
    return max(duration / 60, 1)


def _self_heal_per_min(p, minutes):
    return max(0, p.get("totalHeal", 0) - p.get("totalHealsOnTeammates", 0)) / minutes


def game_stats(match, timeline, puuid):
    p = _participant(match, puuid)
    if p is None:
        return None
    minutes = _minutes(match)
    stats = {
        "damage_per_min": {
            "physical": p.get("physicalDamageDealtToChampions", 0) / minutes,
            "magic": p.get("magicDamageDealtToChampions", 0) / minutes,
            "true": p.get("trueDamageDealtToChampions", 0) / minutes,
        },
        "self_heal_per_min": _self_heal_per_min(p, minutes),
        "lane_gold_diff_14": None,
        "gold_share_gain": None,
    }
    try:
        pm = parse_match(match, timeline)
    except UnsupportedMatch:
        return stats
    if pm.duration_s < 900:
        return stats
    pid = p["participantId"]
    me = pm.players[pid]
    at_14 = frame_at_or_before(pm, 840)
    last = pm.frames[-1]
    opponent = next((q.participant_id for q in pm.players.values()
                     if me.position and q.team_id != me.team_id and q.position == me.position), None)
    if opponent:
        stats["lane_gold_diff_14"] = at_14.gold[pid] - at_14.gold[opponent]
    share_14 = at_14.gold[pid] / max(pm.team_total(at_14, "gold", me.team_id), 1)
    share_end = last.gold[pid] / max(pm.team_total(last, "gold", me.team_id), 1)
    stats["gold_share_gain"] = share_end - share_14
    return stats


def self_heal_baseline(layer: DataLayer, limit=200):
    """Sorted self-heal/min of every participant in recently stored matches, used to judge 'a lot of healing'."""
    values = []
    for match in layer.store.recent_matches(limit):
        minutes = _minutes(match)
        values.extend(_self_heal_per_min(p, minutes) for p in match["info"]["participants"])
    return sorted(values)


def percentile(sorted_values, value):
    if not sorted_values:
        return None
    return bisect_left(sorted_values, value) / len(sorted_values)


def enemy_profile(layer: DataLayer, champions, history: PlayerHistory, heal_baseline):
    entry = history.entry
    if history.champion_match_ids:
        ids, source = history.champion_match_ids[:MAX_GAMES], f"{entry.champion} games"
    else:
        ids, source = [r["match_id"] for r in history.recent][:MAX_GAMES], "recent games (any champion)"
    games = []
    for match_id in ids:
        data = layer.store.get_match(match_id)
        stats = game_stats(*data, entry.puuid) if data else None
        if stats:
            games.append(stats)

    profile = {"riot_id": entry.riot_id, "champion": entry.champion, "games": len(games), "source": source}
    if not games:
        info = next((c["info"] for c in champions.values() if c["id"] == entry.champion), None)
        if info:
            total = max(info["attack"] + info["magic"], 1)
            profile["damage_per_min"] = {"physical": info["attack"] / total, "magic": info["magic"] / total, "true": 0}
        else:
            profile["damage_per_min"] = {"physical": 0.5, "magic": 0.5, "true": 0}
        profile.update(source="champion data (no history)", self_heal_per_min=None, heal_percentile=None, tempo=[])
        return profile

    damage = {k: mean(g["damage_per_min"][k] for g in games) for k in ("physical", "magic", "true")}
    heal = mean(g["self_heal_per_min"] for g in games)
    lane = [g["lane_gold_diff_14"] for g in games if g["lane_gold_diff_14"] is not None]
    trend = [g["gold_share_gain"] for g in games if g["gold_share_gain"] is not None]
    # TODO: tempo is a rough proxy (lane gold @14 and gold-share growth); a better signal would be win rate by
    #  game length per champion across all stored players once the store is large enough.
    tempo = []
    if lane and mean(lane) >= EARLY_LANE_GOLD:
        tempo.append("strong early")
    if trend and mean(trend) >= SCALING_SHARE_GAIN:
        tempo.append("scales late")
    profile.update(
        damage_per_min={k: round(v) for k, v in damage.items()},
        self_heal_per_min=round(heal),
        heal_percentile=percentile(heal_baseline, heal),
        lane_gold_diff_14=round(mean(lane)) if lane else None,
        tempo=tempo,
    )
    return profile


def counter_itemization(profiles):
    totals = {k: sum(p["damage_per_min"][k] for p in profiles) for k in ("physical", "magic", "true")}
    grand = sum(totals.values()) or 1
    split = {k: round(v / grand, 2) for k, v in totals.items()}
    if split["magic"] >= RESIST_SPLIT:
        resist = "Magic resist first: enemy damage is mostly magic"
    elif split["physical"] >= RESIST_SPLIT:
        resist = "Armor first: enemy damage is mostly physical"
    else:
        resist = "Mixed damage: build resists against whoever is ahead"

    healers = [p for p in profiles if (p.get("heal_percentile") or 0) >= HEALER_PERCENTILE]
    heavy = [p for p in healers if p["heal_percentile"] >= HEAVY_HEALER_PERCENTILE]
    if heavy or len(healers) >= 2:
        urgency = "high"
    elif healers:
        urgency = "consider"
    else:
        urgency = "low"
    timing = None
    if healers:
        early = any("strong early" in p["tempo"] for p in healers)
        timing = "by your first or second item" if early else "by your third item"
    return {
        "damage_split": split,
        "resist_advice": resist,
        "grievous_wounds": {
            "urgency": urgency,
            "timing": timing,
            "healers": [{"champion": p["champion"], "self_heal_per_min": p["self_heal_per_min"],
                         "percentile": round(p["heal_percentile"], 2)} for p in healers],
        },
    }
