from dataclasses import dataclass
from statistics import mean

from causal_analysis import analyze_puuid
from data_layer import LIVE, DataLayer

from .roster import RosterEntry


@dataclass
class PlayerHistory:
    entry: RosterEntry
    recent: list[dict]
    champion_match_ids: list[str]

    def rows(self):
        out = []
        for result in self.recent:
            row = next((p for p in result["players"] if p["puuid"] == self.entry.puuid), None)
            if row:
                out.append(row)
        return out

    def summary(self):
        rows = self.rows()
        wins = [r for r in rows if r["win"]]
        carried = [r for r in wins if r["carried"]]
        return {
            "games": len(rows),
            "wins": len(wins),
            "carried_wins": len(carried),
            "carry_rate": len(carried) / len(wins) if wins else 0.0,
            "avg_impact": round(mean(r["impact_ratio"] for r in rows), 2) if rows else None,
            "champion_games": len(self.champion_match_ids),
        }


def load_history(layer: DataLayer, entry: RosterEntry, depth, before_ms, priority=LIVE):
    """Run the player's recent games (before `before_ms`) through Tool 1, reusing anything already stored."""
    recent = analyze_puuid(layer, entry.puuid, depth, priority=priority, end_time=before_ms // 1000 - 1)
    # TODO: Match-V5 can't filter by champion, so champion-specific stats only see games already in the store.
    #  Consider paging deeper (match detail only, no timeline) when a player has few games on their current pick.
    champion_ids = layer.store.player_match_ids(entry.puuid, entry.champion, before_ms)
    return PlayerHistory(entry, recent, champion_ids)
