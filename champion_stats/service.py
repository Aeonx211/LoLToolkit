from data_layer import BULK, DataDragon, DataLayer

from .backfill import backfill
from .rows import PETS, game_row
from .rune_labels import RUNE_VALUE_LABELS, SHARD_NAMES, VERIFIED_RUNES

# (Riot ID, focus champion) pairs the tool is set up for; the tab and CLI default to the first.
TRACKED_PLAYERS = [("Aeoen#NA1", "Lillia")]
QUEUES = {"solo": (420,), "flex": (440,), "both": (420, 440)}
DEFAULT_TARGET = 100


def _static(dd):
    """(Data Dragon item data, names for items/runes/trees). Empty when Data Dragon is unreachable: rows then have no
    item build and the UI falls back to ids."""
    if dd is None:
        return None, {}
    try:
        items, trees = dd.items(), dd.runes()
    except OSError:
        return None, {}
    runes = {r["id"]: r["name"] for t in trees for slot in t["slots"] for r in slot["runes"]}
    return items, {"items": {int(k): v["name"] for k, v in items.items()}, "runes": runes,
                   "trees": {t["id"]: t["name"] for t in trees}}


def _names(rows, static_names):
    """Only the names the rows use, so the browser cache stays small."""
    items = {i for r in rows for i in r["items"] + [r["boots"], r["pet"]] if i}
    runes = {i for r in rows for i in r["runes"]}
    trees = {t for r in rows for t in (r["primary_tree"], r["secondary_tree"]) if t}
    pick = lambda table, ids: {i: table[i] for i in ids if i in table}
    return {
        "items": {**pick(static_names.get("items", {}), items), **pick(PETS, items)},
        "runes": pick(static_names.get("runes", {}), runes),
        "trees": pick(static_names.get("trees", {}), trees),
        "shards": SHARD_NAMES,
        "rune_labels": pick(RUNE_VALUE_LABELS, {int(i) for i in runes}),
        "rune_labels_verified": sorted(i for i in runes if i in VERIFIED_RUNES and i in RUNE_VALUE_LABELS),
    }


def load_rows(layer: DataLayer, riot_id, champion, queue="solo", target=DEFAULT_TARGET, progress=None,
              priority=BULK, dd: DataDragon | None = None):
    """Backfill the player's focus-champion games and return one game row per stored, non-remake game, plus the
    display names the rows refer to."""
    if queue not in QUEUES:
        raise ValueError(f"queue must be one of {', '.join(QUEUES)}")
    if progress:
        progress(f"Looking up {riot_id}")
    puuid = layer.resolve_riot_id(riot_id)
    ids = backfill(layer, puuid, champion, QUEUES[queue], target, progress, priority)
    items, static_names = _static(dd)
    rows = [game_row(*layer.store.get_match(match_id), puuid, items) for match_id in ids]
    rows = [r for r in rows if r]
    return {"puuid": puuid, "riot_id": riot_id, "champion": champion, "queue": queue, "rows": rows,
            "names": _names(rows, static_names)}
