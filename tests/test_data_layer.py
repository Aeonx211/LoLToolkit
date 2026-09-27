import json
import unittest

from causal_analysis import ANALYSIS_VERSION, analyze
from causal_analysis.service import _player_rows
from data_layer import BULK, LIVE, RateLimiter, RiotApiError, RiotClient, Store

from .fixtures import base_damage, build_match, gold_from_diff


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


class RateLimiterTests(unittest.TestCase):
    def test_waits_when_window_full(self):
        clock = FakeClock()
        limiter = RateLimiter([(2, 1.0)], bulk_reserve=0, clock=clock, sleep=clock.sleep)
        for _ in range(3):
            limiter.acquire(LIVE)
        self.assertGreaterEqual(clock.slept, 1.0)

    def test_bulk_leaves_headroom_for_live(self):
        clock = FakeClock()
        limiter = RateLimiter([(10, 1.0)], bulk_reserve=0.2, clock=clock, sleep=clock.sleep)
        for _ in range(8):
            limiter.acquire(BULK)
        self.assertEqual(clock.slept, 0)
        limiter.acquire(LIVE)
        limiter.acquire(LIVE)
        self.assertEqual(clock.slept, 0)
        limiter.acquire(BULK)
        self.assertGreater(clock.slept, 0)

    def test_block_for_delays_next_request(self):
        clock = FakeClock()
        limiter = RateLimiter([(100, 1.0)], clock=clock, sleep=clock.sleep)
        limiter.block_for(5)
        limiter.acquire(LIVE)
        self.assertGreaterEqual(clock.slept, 5)


class ClientTests(unittest.TestCase):
    def make_client(self, responses):
        calls = []

        def transport(url, headers):
            calls.append((url, headers))
            return responses.pop(0)

        client = RiotClient("key", "na1", "americas", transport=transport, sleep=lambda s: None)
        return client, calls

    def test_retries_after_429(self):
        client, calls = self.make_client([(429, {"Retry-After": "0"}, ""), (200, {}, json.dumps(["NA1_1"]))])
        self.assertEqual(client.match_ids("abc"), ["NA1_1"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["X-Riot-Token"], "key")
        self.assertTrue(calls[0][0].startswith("https://americas.api.riotgames.com/lol/match/v5/"))

    def test_404_returns_none(self):
        client, _ = self.make_client([(404, {}, "")])
        self.assertIsNone(client.active_game("abc"))

    def test_auth_error_raises(self):
        client, _ = self.make_client([(403, {}, "Forbidden")])
        with self.assertRaises(RiotApiError) as ctx:
            client.match("NA1_1")
        self.assertEqual(ctx.exception.status, 403)

    def test_riot_id_is_url_encoded(self):
        client, calls = self.make_client([(200, {}, "{}")])
        client.account_by_riot_id("Some Name", "NA1")
        self.assertIn("/by-riot-id/Some%20Name/NA1", calls[0][0])


class StoreTests(unittest.TestCase):
    def carried_match(self):
        def damage(pid, m):
            return base_damage(pid, m) * (3 if pid == 4 else 1)
        kills = [(300 + 60 * i, 4, 6 + i % 5) for i in range(8)]
        return build_match(28, winner=100, gold=gold_from_diff(lambda m: 2000), damage=damage, kills=kills)

    def test_rollup_is_not_double_counted_on_reanalysis(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        match, timeline = self.carried_match()
        store.save_match(match, timeline)
        result = analyze(match, timeline)
        store.save_analysis("NA1_1", ANALYSIS_VERSION, result, _player_rows(result))
        store.save_analysis("NA1_1", ANALYSIS_VERSION, result, _player_rows(result))
        rollup = store.get_rollup("puuid-4")
        self.assertEqual((rollup["games"], rollup["wins"], rollup["carried_wins"]), (1, 1, 1))
        self.assertEqual(rollup["per_champion"]["Champ4"]["carried_wins"], 1)
        self.assertEqual(store.get_rollup("puuid-6")["wins"], 0)
        self.assertEqual(store.get_analysis("NA1_1", ANALYSIS_VERSION)["match_id"], "NA1_1")
        self.assertEqual(store.get_match("NA1_1")[0]["metadata"]["matchId"], "NA1_1")

    def test_account_lookup_is_case_insensitive(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.save_account("p1", "Aeoen", "NA1")
        self.assertEqual(store.find_account("aeoen", "na1"), "p1")


if __name__ == "__main__":
    unittest.main()
