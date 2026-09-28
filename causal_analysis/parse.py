from dataclasses import dataclass, field

TEAMS = (100, 200)
TEAM_NAMES = {100: "Blue", 200: "Red"}

MONSTERS = {
    "DRAGON": "Dragon",
    "BARON_NASHOR": "Baron",
    "RIFTHERALD": "Herald",
    "HORDE": "Grubs",
    "ATAKHAN": "Atakhan",
}


class UnsupportedMatch(ValueError):
    pass


def other_team(team):
    return 200 if team == 100 else 100


@dataclass
class Player:
    participant_id: int
    puuid: str
    team_id: int
    champion: str
    position: str
    riot_id: str
    win: bool
    kills: int
    deaths: int
    assists: int
    damage: int
    gold: int
    objective_damage: int
    items: list[int]


@dataclass
class Frame:
    t: float
    gold: dict[int, int]
    xp: dict[int, int]
    damage: dict[int, int]
    kills: dict[int, int] = field(default_factory=dict)  # running kill count credited to the killer only
    kp: dict[int, int] = field(default_factory=dict)  # running count of team kills each player killed OR assisted

    def get(self, metric):
        return getattr(self, metric)


@dataclass
class Kill:
    t: float
    killer: int
    victim: int
    team: int
    assists: list[int] = field(default_factory=list)


@dataclass
class Objective:
    t: float
    team: int
    kind: str
    detail: str = ""


@dataclass
class ParsedMatch:
    match_id: str
    duration_s: float
    queue_id: int
    game_start: int
    winner: int
    players: dict[int, Player]
    frames: list[Frame]
    kills: list[Kill]
    objectives: list[Objective]

    @property
    def loser(self):
        return other_team(self.winner)

    def team_pids(self, team):
        return [pid for pid, p in self.players.items() if p.team_id == team]

    def team_total(self, frame, metric, team):
        values = frame.get(metric)
        return sum(values.get(pid, 0) for pid in self.team_pids(team))


def parse_match(match, timeline) -> ParsedMatch:
    info = match["info"]
    if {t["teamId"] for t in info["teams"]} != set(TEAMS):
        raise UnsupportedMatch("not a two-team match")
    winner = next((t["teamId"] for t in info["teams"] if t.get("win")), None)
    if winner is None:
        raise UnsupportedMatch("no winning team recorded")

    players = {}
    for p in info["participants"]:
        items = [p.get(f"item{i}", 0) for i in range(7)]
        players[p["participantId"]] = Player(
            participant_id=p["participantId"],
            puuid=p["puuid"],
            team_id=p["teamId"],
            champion=p["championName"],
            position=p.get("teamPosition") or "",
            riot_id=f'{p.get("riotIdGameName", "?")}#{p.get("riotIdTagline", "?")}',
            win=bool(p.get("win")),
            kills=p.get("kills", 0),
            deaths=p.get("deaths", 0),
            assists=p.get("assists", 0),
            damage=p.get("totalDamageDealtToChampions", 0),
            gold=p.get("goldEarned", 0),
            objective_damage=p.get("damageDealtToObjectives", 0),  # towers, dragons, herald, baron combined
            items=[i for i in items if i],
        )
    team_of = {pid: p.team_id for pid, p in players.items()}

    tl_frames = timeline["info"]["frames"]
    events = sorted((e for f in tl_frames for e in f.get("events", [])), key=lambda e: e["timestamp"])
    kills, objectives = [], []
    for e in events:
        t = e["timestamp"] / 1000
        kind = e.get("type")
        if kind == "CHAMPION_KILL":
            victim = e.get("victimId", 0)
            if victim not in team_of:
                continue
            killer = e.get("killerId", 0)
            assists = [pid for pid in e.get("assistingParticipantIds", []) if pid in team_of]
            kills.append(Kill(t, killer if killer in team_of else 0, victim, other_team(team_of[victim]), assists))
        elif kind == "ELITE_MONSTER_KILL":
            team = e.get("killerTeamId") or team_of.get(e.get("killerId"), 0)
            if team not in TEAMS:
                continue
            sub = e.get("monsterSubType", "")
            name = "Elder" if sub == "ELDER_DRAGON" else MONSTERS.get(e.get("monsterType"), "Monster")
            objectives.append(Objective(t, team, name, sub))
        elif kind == "BUILDING_KILL":
            owner = e.get("teamId")
            if owner not in TEAMS:
                continue
            name = "Inhibitor" if e.get("buildingType") == "INHIBITOR_BUILDING" else "Tower"
            objectives.append(Objective(t, other_team(owner), name, e.get("towerType") or e.get("laneType", "")))

    frames = []
    for f in tl_frames:
        gold, xp, damage = {}, {}, {}
        for key, v in f["participantFrames"].items():
            pid = int(key)
            if pid in players:
                gold[pid] = v.get("totalGold", 0)
                xp[pid] = v.get("xp", 0)
                damage[pid] = v.get("damageStats", {}).get("totalDamageDoneToChampions", 0)
        frames.append(Frame(f["timestamp"] / 1000, gold, xp, damage))

    running = {pid: 0 for pid in players}
    running_kp = {pid: 0 for pid in players}
    i = 0
    for frame in frames:
        while i < len(kills) and kills[i].t <= frame.t:
            if kills[i].killer:
                running[kills[i].killer] += 1
                running_kp[kills[i].killer] += 1
            for assist in kills[i].assists:
                running_kp[assist] += 1
            i += 1
        frame.kills = dict(running)
        frame.kp = dict(running_kp)

    duration = info.get("gameDuration", 0)
    if "gameEndTimestamp" not in info:
        duration /= 1000
    return ParsedMatch(
        match_id=match["metadata"]["matchId"],
        duration_s=duration,
        queue_id=info.get("queueId", 0),
        game_start=info.get("gameStartTimestamp") or info.get("gameCreation", 0),
        winner=winner,
        players=players,
        frames=frames,
        kills=kills,
        objectives=objectives,
    )
