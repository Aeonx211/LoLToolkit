import time
from dataclasses import dataclass


@dataclass
class RosterEntry:
    puuid: str
    riot_id: str
    team_id: int
    champion: str
    position: str = ""


@dataclass
class Roster:
    me: str
    players: list[RosterEntry]
    game_start_ms: int
    queue_id: int
    source: str

    @property
    def my_team(self):
        return next(p.team_id for p in self.players if p.puuid == self.me)

    def enemies(self):
        return [p for p in self.players if p.team_id != self.my_team]

    def allies(self):
        return [p for p in self.players if p.team_id == self.my_team]


def from_active_game(game, me, champion_names):
    """Build a roster from a Spectator-V5 active-game payload. champion_names maps numeric champion id -> name."""
    players = [
        RosterEntry(
            puuid=p["puuid"],
            riot_id=p.get("riotId") or "?",
            team_id=p["teamId"],
            champion=champion_names.get(p["championId"], str(p["championId"])),
        )
        for p in game["participants"]
        if p.get("puuid")
    ]
    start = game.get("gameStartTime") or int(time.time() * 1000)
    return Roster(me, players, start, game.get("gameQueueConfigId", 0), "live")


def from_match(match, me):
    """Build a roster from a finished Match-V5 payload, to replay the advisor against a past game."""
    info = match["info"]
    players = [
        RosterEntry(
            puuid=p["puuid"],
            riot_id=f'{p.get("riotIdGameName", "?")}#{p.get("riotIdTagline", "?")}',
            team_id=p["teamId"],
            champion=p["championName"],
            position=p.get("teamPosition") or "",
        )
        for p in info["participants"]
    ]
    start = info.get("gameStartTimestamp") or info["gameCreation"]
    return Roster(me, players, start, info.get("queueId", 0), f"replay of {match['metadata']['matchId']}")
