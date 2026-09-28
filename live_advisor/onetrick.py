from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from data_layer import LIVE, DataLayer

from .roster import RosterEntry

# TODO: first-guess cutoffs; a one-trick is someone who plays one champion in at least 15 of their last 20 games
#  in this queue. With fewer games on record the same share (75%) is required, from MIN_POOL_GAMES up.
POOL_GAMES = 20
ONE_TRICK_GAMES = 15
MIN_POOL_GAMES = 10
LOOKUP_THREADS = 6  # the client's rate limiter still caps the real request rate


def champion_pool(layer: DataLayer, entry: RosterEntry, queue_id, before_ms):
    """Their most-played champion over their last POOL_GAMES games in this queue before this game, or None."""
    ids = layer.recent_match_ids(entry.puuid, POOL_GAMES, queue_id or None, end_time=before_ms // 1000 - 1,
                                 priority=LIVE)
    with ThreadPoolExecutor(max_workers=LOOKUP_THREADS) as pool:
        picks = [p for p in pool.map(lambda i: layer.champion_picked(i, entry.puuid, LIVE), ids) if p]
    if not picks:
        return None
    champion, games = Counter(picks).most_common(1)[0]
    return {
        "champion": champion,
        "games": games,
        "total": len(picks),
        "one_trick": len(picks) >= MIN_POOL_GAMES and games / len(picks) >= ONE_TRICK_GAMES / POOL_GAMES,
        "on_it": champion == entry.champion,
    }
