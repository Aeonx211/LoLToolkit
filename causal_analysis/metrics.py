from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

from .parse import TEAM_NAMES, TEAMS, Frame, ParsedMatch, other_team

# Typical (kill participation, damage, gold) share of team totals by role; used to judge "vastly exceeds their role".
# Unlike damage/gold, KP isn't exclusive: several players can be credited on the same kill, so a role's KP is
# typically 45-65% rather than the ~20% you'd expect from an even split, and the column doesn't sum to 1 across
# the team. TODO: these are rough, commonly-cited averages, not computed from real data. Also role-level
# baselines overrate damage-heavy picks in low-resource roles (e.g. Vel'Koz/Brand support score ~2x a "typical"
# support on damage). Replace with per-champion (or per champion+role) baselines computed from stored matches
# once there's enough data, and scale by game length as the spec suggests.
ROLE_BASELINE = {
    "TOP": (0.45, 0.22, 0.21),
    "JUNGLE": (0.65, 0.17, 0.19),
    "MIDDLE": (0.60, 0.26, 0.22),
    "BOTTOM": (0.55, 0.26, 0.25),
    "UTILITY": (0.65, 0.09, 0.13),
}
DEFAULT_BASELINE = (0.55, 0.20, 0.20)


def lead_for(value, team):
    """Convert a blue-minus-red value into `team`'s lead."""
    return value if team == 100 else -value


def diff_series(pm: ParsedMatch, metric):
    return [(f.t, pm.team_total(f, metric, 100) - pm.team_total(f, metric, 200)) for f in pm.frames]


def value_at(series, t):
    if t <= series[0][0]:
        return series[0][1]
    for (t0, v0), (t1, v1) in pairwise(series):
        if t <= t1:
            return v1 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return series[-1][1]


def lead_peaks(series):
    """Largest lead each team held and when (earliest time it was reached)."""
    peaks = {}
    for team in TEAMS:
        best_t, best = series[0][0], 0
        for t, v in series:
            if lead_for(v, team) > best:
                best_t, best = t, lead_for(v, team)
        peaks[team] = (best, best_t)
    return peaks


def lead_flips(series, noise=500):
    flips, prev = [], 0
    for t, v in series:
        if abs(v) < noise:
            continue
        sign = 1 if v > 0 else -1
        if prev and sign != prev:
            flips.append(t)
        prev = sign
    return flips


def frame_at_or_before(pm: ParsedMatch, t):
    best = pm.frames[0]
    for f in pm.frames:
        if f.t <= t:
            best = f
    return best


def _share(values, pid, team_pids):
    total = sum(values.get(p, 0) for p in team_pids)
    return values.get(pid, 0) / total if total > 0 else 0.0


def _kp_share(pm: ParsedMatch, team, pid, end_kills, start_kills, end_kp, start_kp):
    """Player's (kills+assists) in the window, over the team's actual kills in that window (not a plain _share:
    several players can be credited on the same kill, so this doesn't sum to 1 across the team)."""
    team_kills = sum(end_kills.get(p, 0) - start_kills.get(p, 0) for p in team)
    if team_kills <= 0:
        return 0.0
    return (end_kp.get(pid, 0) - start_kp.get(pid, 0)) / team_kills


def shares_between(pm: ParsedMatch, f0: Frame | None, f1: Frame, pid):
    """(kill participation, damage, gold) share of the player's team gains between two frames (f0=None means
    game start)."""
    team = pm.team_pids(pm.players[pid].team_id)
    kp = _kp_share(pm, team, pid, f1.kills, f0.kills if f0 else {}, f1.kp, f0.kp if f0 else {})
    out = [kp]
    for metric in ("damage", "gold"):
        end = f1.get(metric)
        start = f0.get(metric) if f0 else {}
        deltas = {p: end.get(p, 0) - start.get(p, 0) for p in team}
        out.append(_share(deltas, pid, team))
    return tuple(out)


def impact(shares):
    return sum(shares) / len(shares)


def final_shares(pm: ParsedMatch, pid):
    """(kill participation, damage, gold) share of the player's team totals over the whole game."""
    player = pm.players[pid]
    team = [pm.players[p] for p in pm.team_pids(player.team_id)]
    team_kills = sum(p.kills for p in team)
    kp = (player.kills + player.assists) / team_kills if team_kills else 0.0
    out = [kp]
    for attr in ("damage", "gold"):
        total = sum(getattr(p, attr) for p in team)
        out.append(getattr(player, attr) / total if total else 0.0)
    return tuple(out)


def rolling_impact(pm: ParsedMatch, window_s):
    series = {pid: [] for pid in pm.players}
    for i, frame in enumerate(pm.frames):
        base = frame_at_or_before(pm, frame.t - window_s) if frame.t - window_s > 0 else None
        for pid in pm.players:
            series[pid].append(round(impact(shares_between(pm, base, frame, pid)), 3) if i else 0.0)
    return series


def player_impacts(pm: ParsedMatch):
    rows = []
    for pid, p in sorted(pm.players.items()):
        shares = final_shares(pm, pid)
        baseline = impact(ROLE_BASELINE.get(p.position, DEFAULT_BASELINE))
        value = impact(shares)
        rows.append({
            "participant_id": pid,
            "puuid": p.puuid,
            "riot_id": p.riot_id,
            "team_id": p.team_id,
            "champion": p.champion,
            "position": p.position,
            "win": p.win,
            "kda": [p.kills, p.deaths, p.assists],
            "items": p.items,
            "shares": {"kp": round(shares[0], 3), "damage": round(shares[1], 3), "gold": round(shares[2], 3)},
            "impact": round(value, 3),
            "impact_ratio": round(value / baseline, 3),
            "carried": False,
        })
    return rows


@dataclass
class Moment:
    start: float
    end: float
    kills: dict[int, int]
    objectives: list
    gold_swing: float

    @property
    def beneficiary(self):
        return 100 if self.gold_swing >= 0 else 200

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "kills": {str(k): v for k, v in self.kills.items()},
            "objectives": [{"t": o.t, "team": o.team, "kind": o.kind, "detail": o.detail} for o in self.objectives],
            "gold_swing": round(self.gold_swing),
            "beneficiary": self.beneficiary,
        }


def key_moments(pm: ParsedMatch, gold_series, gap_s):
    """Cluster kills and objectives that happen close together, and measure the gold swing across each cluster."""
    events = sorted([(k.t, k) for k in pm.kills] + [(o.t, o) for o in pm.objectives], key=lambda e: e[0])
    clusters = []
    for ev in events:
        if clusters and ev[0] - clusters[-1][-1][0] <= gap_s:
            clusters[-1].append(ev)
        else:
            clusters.append([ev])
    moments = []
    for cluster in clusters:
        start, end = cluster[0][0], cluster[-1][0]
        kills = {100: 0, 200: 0}
        objectives = []
        for _, ev in cluster:
            if hasattr(ev, "victim"):
                kills[ev.team] += 1
            else:
                objectives.append(ev)
        swing = value_at(gold_series, min(end + 45, pm.duration_s)) - value_at(gold_series, max(start - 15, 0))
        moments.append(Moment(start, end, kills, objectives, swing))
    return moments


def mmss(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def fmt_gold(value):
    value = abs(value)
    return f"{value / 1000:.1f}k" if value >= 1000 else str(int(value))


def describe_moment(m: dict):
    team = m["beneficiary"]
    ours, theirs = m["kills"][str(team)], m["kills"][str(other_team(team))]
    phrases = []
    if ours + theirs >= 2:
        phrases.append(f"won a {ours}-{theirs} fight" if ours > theirs else f"traded kills {ours}-{theirs}")
    elif ours == 1:
        phrases.append("got a pick")
    taken = Counter(o["kind"] for o in m["objectives"] if o["team"] == team)
    if taken:
        names = [f"{n} {k}s" if n > 1 else k for k, n in taken.items()]
        phrases.append("took " + ", ".join(names))
    action = " and ".join(phrases) or "swung the gold"
    return f"{TEAM_NAMES[team]} {action} at {mmss(m['start'])} ({fmt_gold(m['gold_swing'])} swing)"
