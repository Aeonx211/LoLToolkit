import unittest

from champion_stats import backfill, game_row
from data_layer import DataLayer, Store

from .fixtures import build_match

ME = "puuid-2"  # participant 2: blue jungle in the fixtures


def lillia_match(match_id="NA1_1", duration_min=30, winner=100, queue_id=420, champion="Lillia", **kw):
    match, timeline = build_match(duration_min=duration_min, winner=winner, match_id=match_id, queue_id=queue_id, **kw)
    info = match["info"]
    info["gameVersion"] = "15.19.712.1234"
    for p in info["participants"]:
        p["totalMinionsKilled"] = 10 * p["participantId"]
        p["neutralMinionsKilled"] = 100 if p["participantId"] in (2, 7) else 0
    info["participants"][1]["championName"] = champion
    return match, timeline


class GameRowTests(unittest.TestCase):
    def test_basic_facts(self):
        row = game_row(*lillia_match(), ME)
        self.assertEqual(row["match_id"], "NA1_1")
        self.assertEqual(row["patch"], "15.19")
        self.assertEqual(row["queue"], 420)
        self.assertEqual(row["duration_s"], 1800)
        self.assertTrue(row["win"])
        self.assertEqual(row["role"], "JUNGLE")
        self.assertEqual(row["cs"], 120)

    def test_allies_and_enemies_by_role(self):
        row = game_row(*lillia_match(), ME)
        self.assertEqual(row["enemies"], {"TOP": "Champ6", "JUNGLE": "Champ7", "MIDDLE": "Champ8",
                                          "BOTTOM": "Champ9", "UTILITY": "Champ10"})
        self.assertEqual(row["allies"], {"TOP": "Champ1", "MIDDLE": "Champ3", "BOTTOM": "Champ4", "UTILITY": "Champ5"})

    def test_missing_role_is_left_out(self):
        match, timeline = lillia_match()
        match["info"]["participants"][7]["teamPosition"] = ""
        row = game_row(match, timeline, ME)
        self.assertNotIn("MIDDLE", row["enemies"])
        self.assertEqual(len(row["enemies"]), 4)

    def test_loss(self):
        self.assertFalse(game_row(*lillia_match(winner=200), ME)["win"])

    def test_remake_gives_no_row(self):
        self.assertIsNone(game_row(*lillia_match(duration_min=3), ME))

    def test_early_surrender_gives_no_row(self):
        match, timeline = lillia_match()
        for p in match["info"]["participants"]:
            p["gameEndedInEarlySurrender"] = True
        self.assertIsNone(game_row(match, timeline, ME))

    def test_player_not_in_match(self):
        self.assertIsNone(game_row(*lillia_match(), "someone-else"))


class FakeClient:
    """Serves a fixed match history; counts what was fetched."""

    def __init__(self, games):
        self.games = {m["metadata"]["matchId"]: (m, t) for m, t in games}
        self.order = sorted(self.games, key=lambda i: int(i.split("_")[1]), reverse=True)
        self.match_calls, self.timeline_calls = [], []

    def match_ids(self, puuid, count=20, start=0, queue=None, priority=None, **kw):
        ids = [i for i in self.order if queue is None or self.games[i][0]["info"]["queueId"] == queue]
        return ids[start:start + count]

    def match(self, match_id, priority=None):
        self.match_calls.append(match_id)
        return self.games[match_id][0]

    def timeline(self, match_id, priority=None):
        self.timeline_calls.append(match_id)
        return self.games[match_id][1]


def history(n, lillia_every=2):
    """n solo games, newest first by id; every `lillia_every`th one on Lillia."""
    return [lillia_match(f"NA1_{i}", champion="Lillia" if i % lillia_every == 0 else "Graves") for i in range(1, n + 1)]


class BackfillTests(unittest.TestCase):
    def layer(self, games):
        client = FakeClient(games)
        store = Store(":memory:")
        self.addCleanup(store.close)
        return DataLayer(client, store), client

    def test_keeps_only_focus_champion_and_fetches_only_their_timelines(self):
        layer, client = self.layer(history(10))
        ids = backfill(layer, ME, "Lillia", (420,), target=100)
        self.assertEqual(sorted(ids), sorted(f"NA1_{i}" for i in (2, 4, 6, 8, 10)))
        self.assertEqual(sorted(client.timeline_calls), sorted(ids))

    def test_champion_name_is_case_insensitive(self):
        layer, _ = self.layer(history(4))
        self.assertEqual(len(backfill(layer, ME, "lillia", (420,), target=100)), 2)

    def test_stops_at_target_newest_first(self):
        layer, client = self.layer(history(300))
        ids = backfill(layer, ME, "Lillia", (420,), target=3)
        self.assertEqual(ids, ["NA1_300", "NA1_298", "NA1_296"])
        self.assertLess(len(client.match_calls), 20)

    def test_never_refetches_stored_matches(self):
        layer, client = self.layer(history(10))
        backfill(layer, ME, "Lillia", (420,), target=100)
        client.match_calls.clear()
        client.timeline_calls.clear()
        ids = backfill(layer, ME, "Lillia", (420,), target=100)
        self.assertEqual(len(ids), 5)
        self.assertEqual(client.match_calls, [])
        self.assertEqual(client.timeline_calls, [])

    def test_remakes_dont_count_toward_target(self):
        games = [lillia_match("NA1_3"), lillia_match("NA1_2", duration_min=3), lillia_match("NA1_1")]
        layer, _ = self.layer(games)
        self.assertEqual(backfill(layer, ME, "Lillia", (420,), target=2), ["NA1_3", "NA1_1"])

    def test_merges_queues_newest_first(self):
        games = [lillia_match("NA1_1", queue_id=420), lillia_match("NA1_2", queue_id=440),
                 lillia_match("NA1_3", queue_id=420)]
        layer, _ = self.layer(games)
        self.assertEqual(backfill(layer, ME, "Lillia", (420, 440), target=100), ["NA1_3", "NA1_2", "NA1_1"])
        self.assertEqual(backfill(layer, ME, "Lillia", (440,), target=100), ["NA1_2"])

    def test_progress_reports(self):
        layer, _ = self.layer(history(4))
        seen = []
        backfill(layer, ME, "Lillia", (420,), target=100, progress=seen.append)
        self.assertTrue(seen)
        self.assertIn("2 kept", seen[-1])
