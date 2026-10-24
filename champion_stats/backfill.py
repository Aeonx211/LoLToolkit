import heapq

from data_layer import BULK, DataLayer

from .rows import is_remake

PAGE = 100  # Riot's max match ids per request


def _match_number(match_id):
    return int(match_id.rsplit("_", 1)[1])


def _queue_ids(layer, puuid, queue, priority):
    start = 0
    while True:
        ids = layer.client.match_ids(puuid, count=PAGE, start=start, queue=queue, priority=priority)
        yield from ids
        if len(ids) < PAGE:
            return
        start += len(ids)


def backfill(layer: DataLayer, puuid, champion, queues, target=100, progress=None, priority=BULK):
    """Store up to `target` of the player's most recent non-remake games on `champion` in `queues`; return their ids,
    newest first. Riot's match list can't filter by champion, so each unseen candidate is fetched without its
    timeline to check the pick (and remembered), and only focus-champion games get their timeline. Stored matches
    cost no fetches, so re-running only pays for games played since."""
    champion = champion.lower()
    # Match ids grow over time on a shard, so merging each queue's newest-first stream keeps the result newest-first.
    stream = heapq.merge(*(_queue_ids(layer, puuid, q, priority) for q in queues), key=_match_number, reverse=True)
    kept, scanned = [], 0
    for match_id in stream:
        if len(kept) >= target:
            break
        scanned += 1
        pick = layer.game_pick(match_id, puuid, priority)
        if pick and pick[0].lower() == champion:
            data = layer.match_with_timeline(match_id, priority)
            if data and not is_remake(data[0]):
                kept.append(match_id)
        if progress and (scanned % 10 == 0 or len(kept) == target):
            progress(f"Scanned {scanned} games, {len(kept)} kept")
    if progress:
        progress(f"Scanned {scanned} games, {len(kept)} kept" + ("" if len(kept) >= target else " (end of history)"))
    return kept
