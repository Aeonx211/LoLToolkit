from data_layer import LIVE, DataDragon, DataLayer

from .build_predict import predict_build
from .counters import counter_itemization, enemy_profile, self_heal_baseline
from .history import load_history
from .live_client import current_state_by_riot_id, fetch_live_client
from .roster import Roster, from_active_game, from_match
from .threat import rank_carry_threats


def resolve_roster(layer: DataLayer, dd: DataDragon, riot_id, replay=None):
    """The live game the player is in, or a finished match to replay. Raises LookupError with a readable message."""
    me = layer.resolve_riot_id(riot_id)
    if replay:
        data = layer.match_with_timeline(replay, LIVE)
        if data is None:
            raise LookupError(f"Match {replay} not found")
        roster = from_match(data[0], me)
    else:
        game = layer.client.active_game(me)
        if game is None:
            raise LookupError(f"{riot_id} isn't in a game right now. Replay a past match instead.")
        names = {int(c["key"]): c["id"] for c in dd.champions().values()}
        roster = from_active_game(game, me, names)
    if me not in {p.puuid for p in roster.players}:
        raise LookupError(f"{riot_id} isn't in that game")
    return roster


def build_report(layer: DataLayer, dd: DataDragon, roster: Roster, depth=8, include_allies=False, progress=None):
    champions = dd.champions()
    items = dd.items()
    targets = roster.enemies() + (roster.allies() if include_allies else [])
    histories = {}
    for i, entry in enumerate(targets, 1):
        if progress:
            progress(f"[{i}/{len(targets)}] pulling history for {entry.riot_id} ({entry.champion})")
        histories[entry.puuid] = load_history(layer, entry, depth, roster.game_start_ms, LIVE)

    enemy_histories = [histories[e.puuid] for e in roster.enemies()]
    threats = rank_carry_threats(enemy_histories)
    baseline = self_heal_baseline(layer)
    profiles = [enemy_profile(layer, champions, h, baseline) for h in enemy_histories]

    live_state = current_state_by_riot_id(fetch_live_client()) if roster.source == "live" else {}
    enemies = []
    for h, profile in zip(enemy_histories, profiles):
        enemies.append({
            "riot_id": h.entry.riot_id,
            "champion": h.entry.champion,
            "profile": profile,
            "build_prediction": predict_build(layer, items, h),
            "live": live_state.get(h.entry.riot_id.lower()),
        })

    report = {
        "source": roster.source,
        "queue_id": roster.queue_id,
        "focus_target": next((t for t in threats if t["flagged"]), None),
        "carry_threats": threats,
        "counters": counter_itemization(profiles),
        "enemies": enemies,
        "heal_baseline_sample": len(baseline),
    }
    if include_allies:
        report["ally_carries"] = rank_carry_threats([histories[a.puuid] for a in roster.allies()])
    return report
