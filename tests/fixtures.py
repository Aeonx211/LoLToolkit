"""Builders for synthetic Match-V5 match + timeline payloads."""

POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
WEIGHTS = {"TOP": 0.21, "JUNGLE": 0.19, "MIDDLE": 0.22, "BOTTOM": 0.25, "UTILITY": 0.13}
TEAM_GOLD_PER_MIN = 2000


def team_of(pid):
    return 100 if pid <= 5 else 200


def position_of(pid):
    return POSITIONS[(pid - 1) % 5]


def base_gold(pid, minute):
    return 500 + int(TEAM_GOLD_PER_MIN * WEIGHTS[position_of(pid)] * minute)


def base_damage(pid, minute):
    return int(1500 * WEIGHTS[position_of(pid)] * minute * 5)


def gold_from_diff(diff_fn):
    """Per-player gold where blue-minus-red team gold equals diff_fn(minute)."""
    def gold(pid, minute):
        share = diff_fn(minute) * WEIGHTS[position_of(pid)] / 2
        return max(0, int(base_gold(pid, minute) + (share if team_of(pid) == 100 else -share)))
    return gold


def build_match(duration_min=30, winner=100, gold=base_gold, damage=base_damage, kills=(), objectives=(),
                match_id="NA1_1", queue_id=420):
    """kills: (seconds, killer_pid, victim_pid); objectives: (seconds, team, monsterType)."""
    events_by_frame = {}

    def add_event(t, event):
        events_by_frame.setdefault(int(t // 60) + 1, []).append(event)

    for t, killer, victim in kills:
        add_event(t, {"type": "CHAMPION_KILL", "timestamp": int(t * 1000), "killerId": killer,
                      "victimId": victim, "assistingParticipantIds": []})
    for t, team, monster in objectives:
        add_event(t, {"type": "ELITE_MONSTER_KILL", "timestamp": int(t * 1000), "killerTeamId": team,
                      "killerId": 1 if team == 100 else 6, "monsterType": monster})

    frames = []
    for minute in range(duration_min + 1):
        frames.append({
            "timestamp": minute * 60000,
            "participantFrames": {
                str(pid): {
                    "totalGold": gold(pid, minute),
                    "xp": 280 * minute,
                    "damageStats": {"totalDamageDoneToChampions": damage(pid, minute)},
                }
                for pid in range(1, 11)
            },
            "events": events_by_frame.get(minute, []),
        })

    kill_counts = {pid: 0 for pid in range(1, 11)}
    death_counts = {pid: 0 for pid in range(1, 11)}
    for _, killer, victim in kills:
        kill_counts[killer] += 1
        death_counts[victim] += 1

    participants = [
        {
            "participantId": pid,
            "puuid": f"puuid-{pid}",
            "teamId": team_of(pid),
            "championName": f"Champ{pid}",
            "teamPosition": position_of(pid),
            "riotIdGameName": f"Player{pid}",
            "riotIdTagline": "NA1",
            "win": team_of(pid) == winner,
            "kills": kill_counts[pid],
            "deaths": death_counts[pid],
            "assists": 0,
            "totalDamageDealtToChampions": damage(pid, duration_min),
            "goldEarned": gold(pid, duration_min),
            **{f"item{i}": 0 for i in range(7)},
        }
        for pid in range(1, 11)
    ]
    match = {
        "metadata": {"matchId": match_id},
        "info": {
            "gameDuration": duration_min * 60,
            "gameEndTimestamp": 1,
            "gameStartTimestamp": 1_700_000_000_000,
            "queueId": queue_id,
            "teams": [{"teamId": 100, "win": winner == 100}, {"teamId": 200, "win": winner == 200}],
            "participants": participants,
        },
    }
    return match, {"info": {"frames": frames}}
