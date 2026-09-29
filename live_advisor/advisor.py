from concurrent.futures import ThreadPoolExecutor, as_completed

from data_layer import LIVE, DataDragon, DataLayer

from .build_predict import predict_build
from .counters import counter_itemization, enemy_profile
from .healing import assess_enemy, champion_heal_kits, grievous_wounds, item_heal_kinds
from .history import load_history
from .live_client import current_state_by_riot_id, fetch_live_client
from .onetrick import champion_pool
from .roster import Roster, from_active_game, from_match
from .threat import carry_threat_row, rank_carry_threats


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


def build_report(layer: DataLayer, dd: DataDragon, roster: Roster, depth=8, progress=None, on_player=None):
    """Build the live-game report for both teams. Both sides get profile/pool detail (tempo, off-pick/off-role,
    lane gold); only enemies additionally get build prediction and healing, since those feed counter-itemization,
    which only makes sense against the enemy. Each player is reported to `on_player` as soon as their data is
    ready, in completion order, so the UI can render players as they come in instead of waiting on the roster.
    """
    champions = dd.champions()
    items = dd.items()
    kits = champion_heal_kits(dd, progress)
    item_kinds = item_heal_kinds(dd)
    live_state = current_state_by_riot_id(fetch_live_client()) if roster.source == "live" else {}

    def load_enemy(entry):
        if progress:
            progress(f"Pulling history for {entry.riot_id} ({entry.champion})")
        history = load_history(layer, entry, depth, roster.game_start_ms, LIVE)
        pool = champion_pool(layer, entry, roster.queue_id, roster.game_start_ms)
        profile = enemy_profile(layer, champions, history)
        build = predict_build(layer, items, history)
        live = live_state.get(entry.riot_id.lower())
        healing = assess_enemy(entry.champion, kits.get(entry.champion), item_kinds, items, build,
                               (live or {}).get("items", []), "strong early" in profile["tempo"])
        card = {
            "side": "enemy",
            "riot_id": entry.riot_id,
            "champion": entry.champion,
            "profile": profile,
            "build_prediction": build,
            "live": live,
            "healing": healing,
            "pool": pool,
            "impact": carry_threat_row(history),
        }
        return card, history, profile

    def load_ally(entry):
        if progress:
            progress(f"Pulling history for {entry.riot_id} ({entry.champion})")
        history = load_history(layer, entry, depth, roster.game_start_ms, LIVE)
        pool = champion_pool(layer, entry, roster.queue_id, roster.game_start_ms)
        profile = enemy_profile(layer, champions, history)
        card = {
            "side": "ally",
            "riot_id": entry.riot_id,
            "champion": entry.champion,
            "profile": profile,
            "pool": pool,
            "impact": carry_threat_row(history),
        }
        return card, history, None

    jobs = [(e, load_enemy) for e in roster.enemies()] + [(a, load_ally) for a in roster.allies()]
    enemies, enemy_histories, profiles, ally_rows = [], [], [], []
    # One thread per player: the requests are network-bound, and the client's rate limiter still sets the pace.
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [executor.submit(fn, entry) for entry, fn in jobs]
        for future in as_completed(futures):
            card, history, profile = future.result()
            if on_player:
                on_player(card)
            if card["side"] == "enemy":
                enemies.append(card)
                enemy_histories.append(history)
                profiles.append(profile)
            else:
                ally_rows.append({**card["impact"], "profile": card["profile"], "pool": card["pool"]})

    threats = rank_carry_threats(enemy_histories)
    ally_threats = sorted(ally_rows, key=lambda r: r["score"], reverse=True)

    return {
        "source": roster.source,
        "queue_id": roster.queue_id,
        "focus_target": next((t for t in threats if t["flagged"]), None),
        "carry_threats": threats,
        "counters": {**counter_itemization(profiles),
                     "grievous_wounds": grievous_wounds([e["healing"] for e in enemies])},
        "enemies": enemies,
        "ally_carries": ally_threats,
    }
