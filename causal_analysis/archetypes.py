from dataclasses import dataclass

from .metrics import (
    frame_at_or_before,
    impact,
    lead_for,
    lead_peaks,
    shares_between,
    value_at,
)
from .parse import ParsedMatch


# TODO: these are first-guess cutoffs; calibrate against a larger sample of real games (e.g. check the
#  archetype distribution over a few hundred ranked matches and adjust until each tag looks right by eye).
@dataclass(frozen=True)
class Thresholds:
    remake_s: float = 300
    stomp_check_s: float = 900
    stomp_lead: float = 3500
    stomp_max_counter_lead: float = 1000
    stomp_floor: float = 1500
    big_lead: float = 3000
    thrown_kill_lead: int = 2
    snowball_min_lead: float = 1500
    snowball_window_share: float = 0.35
    snowball_ratio: float = 1.5
    snowball_min_kills: int = 3
    carry_ratio: float = 1.35
    carry_min_impact: float = 0.30
    even_band: float = 2500
    even_until_frac: float = 0.75
    even_min_duration_s: float = 1200
    fight_gap_s: float = 30
    rolling_window_s: float = 300


DEFAULT_THRESHOLDS = Thresholds()


def _tag(archetype, team, **detail):
    return {"archetype": archetype, "team": team, "detail": detail}


def turning_point(moments, team, after, before=None):
    """The moment in [after, before] that swung gold hardest toward `team`."""
    candidates = [
        m for m in moments
        if m.start >= after and (before is None or m.start <= before) and lead_for(m.gold_swing, team) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda m: lead_for(m.gold_swing, team)).to_dict()


def recovery_time(gold, team, after):
    """First snapshot after `after` where `team` is no longer behind in gold."""
    return next((t for t, v in gold if t > after and lead_for(v, team) >= 0), None)


def _reversal_point(moments, gold, team, after):
    # Prefer the swing that actually erased the lead over a bigger end-of-game push.
    # TODO: heuristic — gold swing is measured from 60s timeline frames, so two fights close together can
    #  blur into one; consider weighting objectives (Baron/Elder/inhibs) or using XP swing as a tiebreaker.
    recovered = recovery_time(gold, team, after)
    if recovered is not None:
        found = turning_point(moments, team, after, recovered + 60)
        if found:
            return found
    return turning_point(moments, team, after)


def classify(pm: ParsedMatch, gold, kill_diff, moments, players, th: Thresholds = DEFAULT_THRESHOLDS):
    W, L = pm.winner, pm.loser
    peaks = lead_peaks(gold)
    tags = []

    lead_15 = lead_for(value_at(gold, th.stomp_check_s), W)
    after_15 = [lead_for(v, W) for t, v in gold if t >= th.stomp_check_s]
    if (pm.duration_s >= th.stomp_check_s
            and lead_15 >= th.stomp_lead
            and peaks[L][0] <= th.stomp_max_counter_lead
            and min(after_15, default=lead_15) >= th.stomp_floor):
        tags.append(_tag("Stomp", W, lead_at_15=round(lead_15), peak=peaks[W][0], peak_at=peaks[W][1]))

    deficit, deficit_at = peaks[L]
    if deficit >= th.big_lead:
        tags.append(_tag("Comeback", W, deficit=deficit, at=deficit_at,
                         turning_point=_reversal_point(moments, gold, W, deficit_at)))

    thrown = [
        (lead_for(g, L), t)
        for (t, g), (_, k) in zip(gold, kill_diff)
        if lead_for(g, L) >= th.big_lead and lead_for(k, L) >= th.thrown_kill_lead
    ]
    if thrown:
        lead, at = max(thrown, key=lambda x: (x[0], -x[1]))
        tags.append(_tag("Thrown", L, lead=lead, at=at, turning_point=_reversal_point(moments, gold, W, at)))

    snowball = _snowballed_on(pm, gold, peaks, th)
    if snowball:
        tags.append(snowball)

    cutoff = th.even_until_frac * pm.duration_s
    early = [abs(v) for t, v in gold if t <= cutoff]
    if pm.duration_s >= th.even_min_duration_s and early and max(early) <= th.even_band:
        tags.append(_tag("Even-then-decided", None, band=max(early), until=cutoff,
                         decider=turning_point(moments, W, 0.6 * pm.duration_s)))

    winners = [p for p in players if p["team_id"] == W]
    top = max(winners, key=lambda p: p["impact_ratio"])
    if top["impact_ratio"] >= th.carry_ratio and top["impact"] >= th.carry_min_impact:
        top["carried"] = True
        tags.append(_tag("Carried", W, participant_id=top["participant_id"], champion=top["champion"],
                         riot_id=top["riot_id"], position=top["position"], shares=top["shares"],
                         impact_ratio=top["impact_ratio"]))
    return tags


def _snowballed_on(pm: ParsedMatch, gold, peaks, th: Thresholds):
    W, L = pm.winner, pm.loser
    lead, peak_t = peaks[L]
    if lead < th.snowball_min_lead:
        return None
    reversed_at = recovery_time(gold, W, peak_t)
    if reversed_at is None:
        return None
    f_peak = frame_at_or_before(pm, peak_t)
    f_end = frame_at_or_before(pm, min(reversed_at + 120, pm.duration_s))
    best = None
    for pid in pm.team_pids(W):
        window = impact(shares_between(pm, f_peak, f_end, pid))
        before = impact(shares_between(pm, None, f_peak, pid))
        kills = f_end.kills[pid] - f_peak.kills[pid]  # solo kills gotten, not KP: this is about the player
        # personally starting to get picks/kills, which is a different signal from being present for them
        if (window >= th.snowball_window_share
                and window >= th.snowball_ratio * max(before, 0.1)
                and kills >= th.snowball_min_kills
                and (best is None or window > best[1])):
            best = (pid, window, before, kills)
    if best is None:
        return None
    pid, window, before, kills = best
    p = pm.players[pid]
    return _tag("Snowballed-on", L, participant_id=pid, champion=p.champion, riot_id=p.riot_id,
                from_t=peak_t, reversed_at=reversed_at, window_share=round(window, 3),
                before_share=round(before, 3), kills=kills)
