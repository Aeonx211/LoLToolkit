import hashlib

from . import archetypes, metrics
from .archetypes import Thresholds, classify
from .metrics import (
    diff_series,
    key_moments,
    lead_flips,
    lead_peaks,
    player_impacts,
    rolling_impact,
    value_at,
)
from .parse import UnsupportedMatch, parse_match
from .verdict import build_verdict

# Bump when analysis logic changes so cached results are recomputed.
ANALYSIS_VERSION = 3


def analysis_version():
    """Cache key for stored analyses: the logic version plus a hash of the current tuning values."""
    tuned = repr((archetypes.DEFAULT_THRESHOLDS, sorted(metrics.ROLE_BASELINE.items())))
    return f"{ANALYSIS_VERSION}:{hashlib.sha1(tuned.encode()).hexdigest()[:8]}"


def analyze(match, timeline, th: Thresholds | None = None):
    th = th or archetypes.DEFAULT_THRESHOLDS
    match_id = match["metadata"]["matchId"]
    try:
        pm = parse_match(match, timeline)
    except UnsupportedMatch as e:
        return {"match_id": match_id, "version": ANALYSIS_VERSION, "skipped": str(e)}
    if pm.duration_s < th.remake_s or len(pm.frames) < 2:
        return {"match_id": match_id, "version": ANALYSIS_VERSION, "skipped": "remake"}

    gold = diff_series(pm, "gold")
    xp = diff_series(pm, "xp")
    kills = diff_series(pm, "kills")
    moments = key_moments(pm, gold, th.fight_gap_s)
    players = player_impacts(pm)
    tags = classify(pm, gold, kills, moments, players, th)
    gold_peaks, xp_peaks = lead_peaks(gold), lead_peaks(xp)
    top_moments = sorted(moments, key=lambda m: abs(m.gold_swing), reverse=True)[:8]

    return {
        "match_id": match_id,
        "version": ANALYSIS_VERSION,
        "queue_id": pm.queue_id,
        "game_start": pm.game_start,
        "duration_s": pm.duration_s,
        "winner": pm.winner,
        "tags": tags,
        "verdict": build_verdict(pm, gold, tags, moments),
        "leads": {
            "gold_at_15": round(value_at(gold, 900)) if pm.duration_s >= 900 else None,
            "gold_peaks": {str(t): {"lead": v, "at": at} for t, (v, at) in gold_peaks.items()},
            "xp_peaks": {str(t): {"lead": v, "at": at} for t, (v, at) in xp_peaks.items()},
            "gold_flips": lead_flips(gold),
        },
        "key_moments": sorted((m.to_dict() for m in top_moments), key=lambda m: m["start"]),
        "players": players,
        "timeline": {
            "t": [t for t, _ in gold],
            "gold_diff": [v for _, v in gold],
            "xp_diff": [v for _, v in xp],
            "kill_diff": [v for _, v in kills],
            "rolling_impact": {str(pid): s for pid, s in rolling_impact(pm, th.rolling_window_s).items()},
        },
    }
