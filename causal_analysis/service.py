from data_layer import BULK, DataLayer

from .engine import analysis_version, analyze


def _player_rows(result):
    if "skipped" in result:
        return []
    return [
        {
            "puuid": p["puuid"],
            "champion": p["champion"],
            "position": p["position"],
            "win": p["win"],
            "impact_ratio": p["impact_ratio"],
            "carried": p["carried"],
        }
        for p in result["players"]
    ]


def analyze_match_id(layer: DataLayer, match_id, priority=BULK):
    """Return the stored analysis for a match, fetching and analyzing it only if needed."""
    version = analysis_version()
    cached = layer.store.get_analysis(match_id, version)
    if cached:
        return cached
    data = layer.match_with_timeline(match_id, priority)
    if data is None:
        return None
    result = analyze(*data)
    layer.store.save_analysis(match_id, version, result, _player_rows(result))
    return result


def analyze_puuid(layer: DataLayer, puuid, count=10, queue=None, priority=BULK, on_result=None, end_time=None):
    """Analyze a player's `count` most recent real games; remakes and unsupported modes are skipped and don't count."""
    results = []
    start = 0
    while len(results) < count:
        ids = layer.recent_match_ids(puuid, count - len(results), queue, start, end_time, priority)
        if not ids:
            break
        start += len(ids)
        for match_id in ids:
            result = analyze_match_id(layer, match_id, priority)
            if result is None or "skipped" in result:
                continue
            results.append(result)
            if on_result:
                on_result(result)
    return results


def analyze_player(layer: DataLayer, riot_id, count=10, queue=None, priority=BULK, on_result=None):
    puuid = layer.resolve_riot_id(riot_id)
    return puuid, analyze_puuid(layer, puuid, count, queue, priority, on_result)
