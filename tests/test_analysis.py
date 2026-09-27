import json
import math
import unittest

from causal_analysis import analyze

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

    def test_remake_skipped(self):
        result = analyze(*build_match(3))
        self.assertEqual(result["skipped"], "remake")

    def test_result_is_json_serializable(self):
        result = analyze(*build_match(25, gold=gold_from_diff(lambda m: m * 100)))
        self.assertEqual(json.loads(json.dumps(result))["match_id"], "NA1_1")


if __name__ == "__main__":
    unittest.main()
