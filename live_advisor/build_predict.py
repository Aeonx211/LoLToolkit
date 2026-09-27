from collections import Counter
from statistics import mean, median

from data_layer import DataLayer

from .history import PlayerHistory

FULL_CONFIDENCE_GAMES = 8


def is_legendary(item):
    if not item or item.get("into") or not item.get("maps", {}).get("11"):
        return False
    tags = item.get("tags", [])
    return "Consumable" not in tags and "Trinket" not in tags and "Boots" not in tags and item["gold"]["total"] >= 1600


def is_boots(item):
    return bool(item) and "Boots" in item.get("tags", []) and item["gold"]["total"] > 300


def purchase_times(timeline, participant_id):
    times = {}
    for frame in timeline["info"]["frames"]:
        for e in frame.get("events", []):
            if e.get("type") == "ITEM_PURCHASED" and e.get("participantId") == participant_id:
                times.setdefault(e["itemId"], e["timestamp"] / 1000)
    return times


def predict_build(layer: DataLayer, items, history: PlayerHistory, max_games=20):
    """Modal build, typical order, and power-spike timings from a player's games on their current champion."""
    entry = history.entry
    games = []
    for match_id in history.champion_match_ids[:max_games]:
        data = layer.store.get_match(match_id)
        if not data:
            continue
        match, timeline = data
        p = next((q for q in match["info"]["participants"] if q["puuid"] == entry.puuid), None)
        if not p or p["championName"] != entry.champion:
            continue
        final = [p.get(f"item{i}", 0) for i in range(6)]
        times = purchase_times(timeline, p["participantId"])
        order = sorted((i for i in final if is_legendary(items.get(str(i)))), key=lambda i: times.get(i, 1e9))
        boots = next((i for i in final if is_boots(items.get(str(i)))), None)
        games.append({"order": order, "times": [times.get(i) for i in order], "boots": boots})
    games = [g for g in games if g["order"]]
    if not games:
        return None

    n = len(games)
    name = lambda item_id: items.get(str(item_id), {}).get("name", str(item_id))
    counts = Counter(i for g in games for i in set(g["order"]))
    slot = {i: mean(g["order"].index(i) for g in games if i in g["order"]) for i in counts}
    modal = sorted((i for i, _ in counts.most_common(5)), key=lambda i: slot[i])
    firsts = Counter(g["order"][0] for g in games)
    first_item, first_count = firsts.most_common(1)[0]
    boots = Counter(g["boots"] for g in games if g["boots"])
    spikes = []
    for k in range(3):
        times = [g["times"][k] for g in games if len(g["times"]) > k and g["times"][k] is not None]
        if len(times) >= max(1, n // 2):
            spikes.append(round(median(times)))
    top3 = [counts[i] / n for i, _ in counts.most_common(3)]
    return {
        "games": n,
        "modal_build": [{"item": name(i), "rate": round(counts[i] / n, 2)} for i in modal],
        "first_item": {"item": name(first_item), "rate": round(first_count / n, 2)},
        "boots": {"item": name(boots.most_common(1)[0][0]), "rate": round(boots.most_common(1)[0][1] / n, 2)}
        if boots else None,
        "item_spikes_s": spikes,
        "confidence": round(min(1.0, n / FULL_CONFIDENCE_GAMES) * mean(top3), 2),
    }
