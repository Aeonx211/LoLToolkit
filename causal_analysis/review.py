from .metrics import fmt_gold, lead_for, mmss, value_at
from .parse import TEAM_NAMES, ParsedMatch, other_team

# A death/fight before this counts as "early" for invade-style framing.
EARLY_CUTOFF_S = 300
# Minimum lead swing (in the target's favor going the other way) worth calling out.
SWING_THRESHOLD = 300


def _moment_for(moments, t):
    for m in moments:
        if m.start - 1e-6 <= t <= m.end + 1e-6:
            return m
    return None


def _champ(pm: ParsedMatch, pid):
    p = pm.players.get(pid)
    return p.champion if p else None


def _death_finding(pm: ParsedMatch, gold_series, moments, pid, kill):
    team, enemy = pm.players[pid].team_id, other_team(pm.players[pid].team_id)
    m = _moment_for(moments, kill.t)
    lead_before = lead_for(value_at(gold_series, max(kill.t - 1, 0)), team)
    team_kills = m.kills[team] if m else 0
    enemy_kills = m.kills[enemy] if m else 1
    swing = lead_for(m.gold_swing, team) if m else 0
    solo = m is not None and team_kills == 0 and enemy_kills == 1 and not m.objectives

    tags = []
    if team_kills == 0:
        tags.append("no_trade")
    if enemy_kills >= 2 and team_kills < enemy_kills:
        tags.append("lost_fight")
    if solo and kill.t < EARLY_CUTOFF_S:
        tags.append("early_solo")
    if lead_before >= SWING_THRESHOLD and swing <= -SWING_THRESHOLD:
        tags.append("gave_up_lead")

    killer_champ = _champ(pm, kill.killer)
    parts = [f"Died at {mmss(kill.t)}" + (f" to {killer_champ}" if killer_champ else "")]
    if "gave_up_lead" in tags:
        parts[0] = f"Up {fmt_gold(lead_before)}, then " + parts[0][0].lower() + parts[0][1:]
    if "early_solo" in tags:
        parts.append("alone, with no trade back — looks like an overextension or invade that didn't pay off")
    elif "no_trade" in tags:
        parts.append("with no trade back — a free kill for them")
    elif "lost_fight" in tags:
        parts.append(f"in a fight {team_kills}-{enemy_kills} down")
    if m and swing <= -SWING_THRESHOLD:
        parts.append(f"({fmt_gold(swing)} swung to {TEAM_NAMES[enemy]} around that fight)")

    return {
        "t": kill.t,
        "killer_champion": killer_champ,
        "tags": tags,
        "lead_before": round(lead_before),
        "swing": round(swing),
        "position": kill.position,
        "note": ", ".join(parts[:1]) + (" " + " ".join(parts[1:]) if len(parts) > 1 else ""),
    }


def _early_aggression_findings(pm: ParsedMatch, gold_series, moments, pid, own_deaths):
    """Early moments (before EARLY_CUTOFF_S) the player took part in — as killer or assist, not already covered
    by a death finding — that still swung toward the enemy: an invade or skirmish that didn't pay off."""
    team, enemy = pm.players[pid].team_id, other_team(pm.players[pid].team_id)
    death_moments = {id(_moment_for(moments, k.t)) for k in own_deaths}
    findings = []
    for m in moments:
        if m.start >= EARLY_CUTOFF_S or id(m) in death_moments:
            continue
        involved = any(k.killer == pid or pid in k.assists for k in pm.kills if m.start <= k.t <= m.end)
        if not involved:
            continue
        swing = lead_for(m.gold_swing, team)
        if swing <= -SWING_THRESHOLD:
            findings.append({
                "t": m.start,
                "killer_champion": None,
                "tags": ["early_aggression"],
                "lead_before": None,
                "swing": round(swing),
                "position": None,
                "note": f"Took part in a skirmish at {mmss(m.start)} that didn't pay off "
                        f"({fmt_gold(swing)} swung to {TEAM_NAMES[enemy]}).",
            })
    return findings


def review_player(pm: ParsedMatch, gold_series, moments, pid):
    """Post-game breakdown of what may have kept `pid` under their potential: deaths that gave up a lead, came
    with no trade back, or lost a fight outright, plus early skirmishes/invades that swung gold the other way
    without ending in a death. Approximate — a moment's gold swing isn't entirely this one player's doing when
    others were in the same fight — so findings describe the fight, not a precise personal cost."""
    if pid not in pm.players:
        return None
    own_deaths = [k for k in pm.kills if k.victim == pid]
    findings = [_death_finding(pm, gold_series, moments, pid, k) for k in own_deaths]
    findings += _early_aggression_findings(pm, gold_series, moments, pid, own_deaths)
    findings.sort(key=lambda f: f["swing"])

    flagged = [f for f in findings if f["swing"] <= -SWING_THRESHOLD or "early_solo" in f["tags"]]
    total_swing = sum(f["swing"] for f in findings if f["swing"] < 0)
    return {
        "participant_id": pid,
        "deaths": len(own_deaths),
        "findings": findings,
        "flagged_count": len(flagged),
        "total_negative_swing": round(total_swing),
        "summary": (
            f"No standout bad deaths or invades — your deaths look like normal trades."
            if not flagged else
            f"{len(flagged)} moment(s) stand out, totalling roughly {fmt_gold(total_swing)} swung the other way."
        ),
    }
