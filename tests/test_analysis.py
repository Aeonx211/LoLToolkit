import json
import math
import unittest

from causal_analysis import analyze
from causal_analysis.metrics import final_shares, weighted_impact
from causal_analysis.parse import parse_match

from .fixtures import base_damage, base_gold, build_match, gold_from_diff


def archetypes(result):
    return {(t["archetype"], t["team"]) for t in result["tags"]}


def tag(result, name):
    return next(t for t in result["tags"] if t["archetype"] == name)


class ArchetypeTests(unittest.TestCase):
    def test_stomp(self):
        result = analyze(*build_match(25, winner=100, gold=gold_from_diff(lambda m: min(m * 450, 9000))))
        self.assertIn(("Stomp", 100), archetypes(result))
        self.assertNotIn(("Comeback", 100), archetypes(result))
        self.assertTrue(result["verdict"].startswith("Blue stomped"))

    def test_thrown_and_comeback(self):
        def diff(m):
            if m <= 15:
                return -min(m * 300, 4500)
            return -4500 + (m - 15) * 700 + (4000 if m >= 28 else 0)

        # A bigger end-of-game push at 28:00 must not be reported as the turning point.
        kills = [(300, 6, 1), (480, 7, 2), (660, 8, 3),
                 (1320, 1, 6), (1325, 2, 7), (1330, 3, 8), (1335, 4, 9),
                 (1680, 1, 6), (1685, 2, 7), (1690, 3, 8), (1695, 4, 9), (1700, 5, 10)]
        result = analyze(*build_match(30, winner=100, gold=gold_from_diff(diff), kills=kills,
                                      objectives=[(1350, 100, "BARON_NASHOR")]))
        tags = archetypes(result)
        self.assertIn(("Thrown", 200), tags)
        self.assertIn(("Comeback", 100), tags)
        thrown = tag(result, "Thrown")["detail"]
        self.assertEqual(thrown["lead"], 4500)
        self.assertEqual(thrown["at"], 900)
        self.assertEqual(thrown["turning_point"]["start"], 1320)
        self.assertIn("Blue won a 4-0 fight and took Baron at 22:00", result["verdict"])

    def test_even_then_decided(self):
        def diff(m):
            return 1500 * math.sin(m) if m <= 28 else 4000

        kills = [(1710, 1, 6), (1715, 2, 7), (1720, 3, 8)]
        result = analyze(*build_match(31, winner=100, gold=gold_from_diff(diff), kills=kills,
                                      objectives=[(1730, 100, "BARON_NASHOR")]))
        self.assertIn(("Even-then-decided", None), archetypes(result))
        self.assertEqual(tag(result, "Even-then-decided")["detail"]["decider"]["start"], 1710)

    def test_carried(self):
        def damage(pid, m):
            return base_damage(pid, m) * (3 if pid == 4 else 1)

        kills = [(300 + 60 * i, 4, 6 + i % 5) for i in range(8)]
        result = analyze(*build_match(28, winner=100, gold=gold_from_diff(lambda m: 2000 if m >= 10 else 0),
                                      damage=damage, kills=kills))
        carried = tag(result, "Carried")
        self.assertEqual(carried["detail"]["participant_id"], 4)
        self.assertTrue(next(p for p in result["players"] if p["participant_id"] == 4)["carried"])

    def test_co_carried(self):
        """Two standouts close to each other, but clearly ahead of the rest of the team, both get tagged."""
        def damage(pid, m):
            return base_damage(pid, m) * (2.6 if pid in (1, 3) else 1)

        kills = [(300 + 60 * i, 1 if i % 2 == 0 else 3, 6 + i % 5) for i in range(8)]
        result = analyze(*build_match(28, winner=100, gold=gold_from_diff(lambda m: 2000 if m >= 10 else 0),
                                      damage=damage, kills=kills))
        carried_tags = [t for t in result["tags"] if t["archetype"] == "Carried"]
        self.assertEqual({t["detail"]["participant_id"] for t in carried_tags}, {1, 3})
        for pid in (1, 3):
            self.assertTrue(next(p for p in result["players"] if p["participant_id"] == pid)["carried"])
        self.assertIn("co-carried", result["verdict"])

    def test_snowballed_on(self):
        def gold(pid, m):
            value = base_gold(pid, m)
            if pid > 5:
                value += 40 * min(m, 10)
            if pid == 3 and m > 12:
                value += 1000 * (m - 12)
            return value

        kills = [(750, 3, 6), (780, 3, 7), (810, 3, 8), (870, 3, 9), (930, 3, 10)]
        result = analyze(*build_match(30, winner=100, gold=gold, kills=kills))
        snowball = tag(result, "Snowballed-on")
        self.assertEqual(snowball["team"], 200)
        self.assertEqual(snowball["detail"]["participant_id"], 3)
        self.assertEqual(snowball["detail"]["reversed_at"], 840)

    def test_tower_and_neutral_damage_are_tracked_separately(self):
        def tower_damage(pid, m):
            return 100 * m if pid == 1 else 10 * m

        def neutral_damage(pid, m):
            return 100 * m if pid == 2 else 0

        result = analyze(*build_match(20, tower_damage=tower_damage, neutral_damage=neutral_damage))
        team1 = [p for p in result["players"] if p["team_id"] == 100]
        self.assertNotIn("objectives", team1[0]["shares"])
        self.assertEqual(max(team1, key=lambda p: p["shares"]["tower"])["participant_id"], 1)
        self.assertEqual(max(team1, key=lambda p: p["shares"]["neutral"])["participant_id"], 2)

    def test_remake_skipped(self):
        result = analyze(*build_match(3))
        self.assertEqual(result["skipped"], "remake")

    def test_result_is_json_serializable(self):
        result = analyze(*build_match(25, gold=gold_from_diff(lambda m: m * 100)))
        self.assertEqual(json.loads(json.dumps(result))["match_id"], "NA1_1")


class WeightedImpactTests(unittest.TestCase):
    """Unit tests for the death bonus and per-component cap in metrics.weighted_impact, isolated from a full
    match (final_shares/ROLE_BASELINE already have their own coverage via ArchetypeTests)."""

    def setUp(self):
        from causal_analysis.metrics import ROLE_BASELINE
        self.baseline = ROLE_BASELINE["MIDDLE"]

    def test_death_bonus_only_ever_helps(self):
        kp, damage, gold, tower, neutral, survival = self.baseline
        baseline_value = weighted_impact(self.baseline)
        fewer_deaths = (kp, damage, gold, tower, neutral, survival + 0.05)  # above the role's survival baseline
        more_deaths = (kp, damage, gold, tower, neutral, survival - 0.05)  # below it
        self.assertGreater(weighted_impact(fewer_deaths, self.baseline), baseline_value)
        self.assertEqual(weighted_impact(more_deaths, self.baseline), baseline_value)  # bonus-only: no penalty

    def test_share_cap_limits_one_component_from_swinging_the_ratio(self):
        kp, damage, gold, tower, neutral, survival = self.baseline
        shares_10x = (kp, damage * 10, gold, tower, neutral, survival)
        shares_100x = (kp, damage * 100, gold, tower, neutral, survival)
        capped_10x = weighted_impact(shares_10x, self.baseline)
        capped_100x = weighted_impact(shares_100x, self.baseline)
        uncapped_10x = weighted_impact(shares_10x, None)
        self.assertEqual(capped_10x, capped_100x)  # cap plateaus regardless of how far above baseline it goes
        self.assertLess(capped_10x, uncapped_10x)  # capping actually reduced it vs. no baseline/no cap


class CarriedSelectionTests(unittest.TestCase):
    """Unit tests for the margin-based co-carry rule in archetypes._carried, isolated from a full match."""

    def setUp(self):
        from causal_analysis.archetypes import Thresholds, _carried
        self.carried = _carried
        self.th = Thresholds(carry_ratio=1.20, carry_margin=0.15, carry_min_impact=0.0)

    def _players(self, *ratios):
        return [{"team_id": 100, "impact_ratio": r, "impact": 1.0} for r in ratios]

    def test_lone_standout_carries_alone(self):
        result = self.carried(self._players(1.40, 1.10, 0.90, 0.80, 0.70), 100, self.th)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["impact_ratio"], 1.40)

    def test_close_pair_above_the_rest_both_carry(self):
        result = self.carried(self._players(1.30, 1.29, 0.90, 0.80, 0.70), 100, self.th)
        self.assertEqual({p["impact_ratio"] for p in result}, {1.30, 1.29})

    def test_nobody_clears_the_floor(self):
        result = self.carried(self._players(1.10, 1.05, 1.00, 0.95, 0.90), 100, self.th)
        self.assertEqual(result, [])

    def test_only_winning_team_is_considered(self):
        players = self._players(1.40, 1.10, 0.90, 0.80, 0.70)
        for p in players:
            p["team_id"] = 200
        self.assertEqual(self.carried(players, 100, self.th), [])


if __name__ == "__main__":
    unittest.main()
