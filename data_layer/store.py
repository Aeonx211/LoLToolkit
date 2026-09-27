import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    puuid TEXT PRIMARY KEY,
    game_name TEXT NOT NULL,
    tag_line TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS accounts_riot_id ON accounts (lower(game_name), lower(tag_line));

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    game_start INTEGER,
    duration_s INTEGER,
    queue_id INTEGER,
    game_version TEXT,
    match_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    match_id TEXT NOT NULL,
    puuid TEXT NOT NULL,
    participant_id INTEGER,
    team_id INTEGER,
    champion_name TEXT,
    position TEXT,
    win INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    items TEXT,
    PRIMARY KEY (match_id, puuid)
);
CREATE INDEX IF NOT EXISTS participants_puuid ON participants (puuid, champion_name);

CREATE TABLE IF NOT EXISTS analyses (
    match_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    result_json TEXT NOT NULL,
    analyzed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS player_match_impact (
    match_id TEXT NOT NULL,
    puuid TEXT NOT NULL,
    champion_name TEXT,
    position TEXT,
    win INTEGER NOT NULL,
    impact_ratio REAL,
    carried INTEGER NOT NULL,
    PRIMARY KEY (match_id, puuid)
);

CREATE TABLE IF NOT EXISTS player_rollup (
    puuid TEXT PRIMARY KEY,
    games INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    carried_wins INTEGER NOT NULL,
    per_champion TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

ACCOUNT_TTL_S = 7 * 24 * 3600


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.RLock()

    def close(self):
        self._db.close()

    def find_account(self, game_name, tag_line):
        with self._lock:
            row = self._db.execute(
                "SELECT puuid, fetched_at FROM accounts WHERE lower(game_name)=lower(?) AND lower(tag_line)=lower(?)",
                (game_name, tag_line),
            ).fetchone()
        if row and time.time() - row[1] < ACCOUNT_TTL_S:
            return row[0]
        return None

    def save_account(self, puuid, game_name, tag_line):
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO accounts VALUES (?, ?, ?, ?)", (puuid, game_name, tag_line, time.time())
            )

    def get_match(self, match_id):
        with self._lock:
            row = self._db.execute(
                "SELECT match_json, timeline_json FROM matches WHERE match_id=?", (match_id,)
            ).fetchone()
        return (json.loads(row[0]), json.loads(row[1])) if row else None

    def has_match(self, match_id):
        with self._lock:
            return self._db.execute("SELECT 1 FROM matches WHERE match_id=?", (match_id,)).fetchone() is not None

    def save_match(self, match, timeline):
        info = match["info"]
        match_id = match["metadata"]["matchId"]
        duration = info.get("gameDuration", 0)
        if "gameEndTimestamp" not in info:
            duration //= 1000
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (match_id, info.get("gameStartTimestamp") or info.get("gameCreation"), duration,
                 info.get("queueId"), info.get("gameVersion"), json.dumps(match), json.dumps(timeline), time.time()),
            )
            self._db.executemany(
                "INSERT OR REPLACE INTO participants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (match_id, p["puuid"], p.get("participantId"), p.get("teamId"), p.get("championName"),
                     p.get("teamPosition") or "", int(bool(p.get("win"))), p.get("kills"), p.get("deaths"),
                     p.get("assists"), json.dumps([p.get(f"item{i}", 0) for i in range(7)]))
                    for p in info["participants"]
                ],
            )

    def player_match_ids(self, puuid, champion=None, before_ms=None, limit=50):
        """Stored matches for a player, newest first, optionally only on one champion / before a timestamp."""
        sql = ("SELECT p.match_id FROM participants p JOIN matches m ON m.match_id = p.match_id "
               "WHERE p.puuid = ?")
        args = [puuid]
        if champion:
            sql += " AND p.champion_name = ?"
            args.append(champion)
        if before_ms:
            sql += " AND m.game_start < ?"
            args.append(before_ms)
        sql += " ORDER BY m.game_start DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            return [row[0] for row in self._db.execute(sql, args).fetchall()]

    def recent_matches(self, limit=200):
        with self._lock:
            rows = self._db.execute(
                "SELECT match_json FROM matches ORDER BY game_start DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get_analysis(self, match_id, version):
        with self._lock:
            row = self._db.execute(
                "SELECT result_json FROM analyses WHERE match_id=? AND version=?", (match_id, version)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_analysis(self, match_id, version, result, player_rows):
        """Store an analysis and fold its per-player rows into the rollups, replacing any previous version."""
        with self._lock, self._db:
            old = self._db.execute(
                "SELECT puuid, champion_name, win, carried FROM player_match_impact WHERE match_id=?", (match_id,)
            ).fetchall()
            for puuid, champion, win, carried in old:
                self._apply_rollup(puuid, champion, win, carried, -1)
            self._db.execute("DELETE FROM player_match_impact WHERE match_id=?", (match_id,))
            for r in player_rows:
                self._db.execute(
                    "INSERT INTO player_match_impact VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (match_id, r["puuid"], r["champion"], r["position"], int(r["win"]),
                     r["impact_ratio"], int(r["carried"])),
                )
                self._apply_rollup(r["puuid"], r["champion"], int(r["win"]), int(r["carried"]), 1)
            self._db.execute(
                "INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?)",
                (match_id, version, json.dumps(result), time.time()),
            )

    def _apply_rollup(self, puuid, champion, win, carried, sign):
        row = self._db.execute(
            "SELECT games, wins, carried_wins, per_champion FROM player_rollup WHERE puuid=?", (puuid,)
        ).fetchone()
        games, wins, carried_wins, per = row if row else (0, 0, 0, "{}")
        per = json.loads(per)
        champ = per.setdefault(champion, {"games": 0, "wins": 0, "carried_wins": 0})
        carried_win = int(bool(win and carried))
        champ["games"] += sign
        champ["wins"] += sign * win
        champ["carried_wins"] += sign * carried_win
        if champ["games"] <= 0:
            del per[champion]
        self._db.execute(
            "INSERT OR REPLACE INTO player_rollup VALUES (?, ?, ?, ?, ?, ?)",
            (puuid, games + sign, wins + sign * win, carried_wins + sign * carried_win, json.dumps(per), time.time()),
        )

    def get_rollup(self, puuid):
        with self._lock:
            row = self._db.execute(
                "SELECT games, wins, carried_wins, per_champion FROM player_rollup WHERE puuid=?", (puuid,)
            ).fetchone()
        if not row:
            return None
        games, wins, carried_wins, per = row
        return {
            "games": games,
            "wins": wins,
            "carried_wins": carried_wins,
            "carry_rate_in_wins": carried_wins / wins if wins else 0.0,
            "per_champion": json.loads(per),
        }
