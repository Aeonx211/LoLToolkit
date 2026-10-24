from data_layer import BULK, DataLayer

from .backfill import backfill
from .rows import game_row

# (Riot ID, focus champion) pairs the tool is set up for; the tab and CLI default to the first.
TRACKED_PLAYERS = [("Aeoen#NA1", "Lillia")]
QUEUES = {"solo": (420,), "flex": (440,), "both": (420, 440)}
DEFAULT_TARGET = 100


def load_rows(layer: DataLayer, riot_id, champion, queue="solo", target=DEFAULT_TARGET, progress=None,
              priority=BULK):
    """Backfill the player's focus-champion games and return one game row per stored, non-remake game."""
    if queue not in QUEUES:
        raise ValueError(f"queue must be one of {', '.join(QUEUES)}")
    if progress:
        progress(f"Looking up {riot_id}")
    puuid = layer.resolve_riot_id(riot_id)
    ids = backfill(layer, puuid, champion, QUEUES[queue], target, progress, priority)
    rows = [game_row(*layer.store.get_match(match_id), puuid) for match_id in ids]
    return {"puuid": puuid, "riot_id": riot_id, "champion": champion, "queue": queue,
            "rows": [r for r in rows if r]}
