from .history import PlayerHistory

# TODO: first-guess cutoffs; calibrate once there's enough stored history to see how often players get flagged.
MIN_WINS_TO_FLAG = 3
CARRY_RATE_TO_FLAG = 0.4
FULL_CONFIDENCE_WINS = 5


def carry_threat_row(h: PlayerHistory):
    """A single player's carry-impact numbers, standalone so callers can stream one at a time."""
    s = h.summary()
    confidence = min(1.0, s["wins"] / FULL_CONFIDENCE_WINS)
    impact_bonus = max(0.0, (s["avg_impact"] or 1.0) - 1.0) * 0.5
    return {
        "puuid": h.entry.puuid,
        "riot_id": h.entry.riot_id,
        "champion": h.entry.champion,
        **s,
        "score": round(s["carry_rate"] * confidence + impact_bonus, 3),
        "flagged": s["wins"] >= MIN_WINS_TO_FLAG and s["carry_rate"] >= CARRY_RATE_TO_FLAG,
    }


def rank_carry_threats(histories: list[PlayerHistory]):
    """Rank players by how often Tool 1 tagged them as the carry in their recent wins."""
    rows = [carry_threat_row(h) for h in histories]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
