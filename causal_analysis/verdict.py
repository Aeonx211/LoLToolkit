from .metrics import describe_moment, fmt_gold, lead_for, mmss, value_at
from .parse import TEAM_NAMES, ParsedMatch


def _pct(x):
    return f"{round(x * 100)}%"


def build_verdict(pm: ParsedMatch, gold, tags, moments):
    W, L = TEAM_NAMES[pm.winner], TEAM_NAMES[pm.loser]
    by = {t["archetype"]: t["detail"] for t in tags}
    sentences = []

    if "Stomp" in by:
        d = by["Stomp"]
        sentences.append(
            f"{W} stomped: up {fmt_gold(d['lead_at_15'])} at 15:00 and {L} never got back in "
            f"(peak +{fmt_gold(d['peak'])} at {mmss(d['peak_at'])})."
        )
    elif "Thrown" in by:
        d = by["Thrown"]
        text = f"{L} was winning by {fmt_gold(d['lead'])} at {mmss(d['at'])} but threw the lead"
        if d["turning_point"]:
            text += f"; the game turned when {describe_moment(d['turning_point'])}"
        sentences.append(text + ".")
    elif "Comeback" in by:
        d = by["Comeback"]
        text = f"{W} came back from {fmt_gold(d['deficit'])} down at {mmss(d['at'])}"
        if d["turning_point"]:
            text += f"; the game turned when {describe_moment(d['turning_point'])}"
        sentences.append(text + ".")
    elif "Even-then-decided" in by:
        d = by["Even-then-decided"]
        text = f"Even game (gold within {fmt_gold(d['band'])} until {mmss(d['until'])})"
        if d["decider"]:
            text += f", decided when {describe_moment(d['decider'])}"
        sentences.append(text + ".")
    else:
        lead_15 = lead_for(value_at(gold, 900), pm.winner)
        text = f"{W} won"
        if pm.duration_s >= 900 and abs(lead_15) >= 500:
            text += f" ({'up' if lead_15 > 0 else 'down'} {fmt_gold(lead_15)} at 15:00)"
        best = max((m for m in moments if lead_for(m.gold_swing, pm.winner) > 0),
                   key=lambda m: lead_for(m.gold_swing, pm.winner), default=None)
        if best:
            text += f"; biggest swing: {describe_moment(best.to_dict())}"
        sentences.append(text + ".")

    if "Snowballed-on" in by:
        d = by["Snowballed-on"]
        sentences.append(
            f"{d['champion']} ({d['riot_id']}) snowballed from {mmss(d['from_t'])}: {d['kills']} kills and "
            f"{_pct(d['window_share'])} of {W}'s impact in the swing window (was {_pct(d['before_share'])})."
        )
    if "Carried" in by:
        d = by["Carried"]
        s = d["shares"]
        role = d["position"].lower() or "player"
        sentences.append(
            f"{d['champion']} ({d['riot_id']}) carried {W}: {_pct(s['kp'])} kill participation, {_pct(s['damage'])} "
            f"of damage, {_pct(s['gold'])} of gold ({d['impact_ratio']:.1f}x a typical {role})."
        )
    return " ".join(sentences)
