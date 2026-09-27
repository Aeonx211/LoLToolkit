import unittest

from data_layer import Store
from live_advisor.build_predict import predict_build
from live_advisor.counters import counter_itemization
from live_advisor.history import PlayerHistory
from live_advisor.roster import RosterEntry, from_match
from live_advisor.threat import rank_carry_threats

from .fixtures import build_match

ITEMS = {
    "3031": {"name": "Infinity Edge", "gold": {"total": 3500}, "maps": {"11": True}, "tags": []},
    "3094": {"name": "Rapid Firecannon", "gold": {"total": 2600}, "maps": {"11": True}, "tags": []},
    "3072": {"name": "Bloodthirster", "gold": {"total": 3400}, "maps": {"11": True}, "tags": []},
    "3006": {"name": "Berserker's Greaves", "gold": {"total": 1100}, "maps": {"11": True}, "tags": ["Boots"]},
    "1038": {"name": "B. F. Sword", "gold": {"total": 1300}, "maps": {"11": True}, "tags": [], "into": ["3031"]},
}


def result_with(puuid, win, carried, impact=1.0):
    return {"match_id": "x", "players": [{"puuid": puuid, "win": win, "carried": carried, "impact_ratio": impact}]}


def history(puuid, outcomes, champion_ids=()):
    entry = RosterEntry(puuid, f"{puuid}#NA1", 200, "Draven")
    return PlayerHistory(entry, [result_with(puuid, w, c, i) for w, c, i in outcomes], list(champion_ids))


class ThreatTests(unittest.TestCase):
    def test_flags_consistent_carry(self):
        carry = history("carry", [(True, True, 1.6)] * 4 + [(False, False, 1.2)])
        passenger = history("passenger", [(True, False, 0.8)] * 5)
        ranked = rank_carry_threats([passenger, carry])
        self.assertEqual(ranked[0]["puuid"], "carry")
        self.assertTrue(ranked[0]["flagged"])
        self.assertFalse(ranked[1]["flagged"])

    def test_small_sample_is_not_flagged(self):
        lucky = history("lucky", [(True, True, 1.5)] * 2)
        self.assertFalse(rank_carry_threats([lucky])[0]["flagged"])


class CounterTests(unittest.TestCase):
    def profile(self, physical, magic, heal_pct=None, tempo=()):
        return {"champion": "X", "damage_per_min": {"physical": physical, "magic": magic, "true": 0},
                "self_heal_per_min": 300, "heal_percentile": heal_pct, "tempo": list(tempo)}

    def test_magic_heavy_team_gets_mr_advice(self):
        c = counter_itemization([self.profile(100, 900), self.profile(200, 800)])
        self.assertTrue(c["resist_advice"].startswith("Magic resist"))

    def test_heavy_early_healer_means_early_grievous_wounds(self):
        c = counter_itemization([self.profile(500, 500, 0.95, ["strong early"]), self.profile(500, 500, 0.2)])
        gw = c["grievous_wounds"]
        self.assertEqual(gw["urgency"], "high")
        self.assertEqual(gw["timing"], "by your first or second item")


class BuildPredictionTests(unittest.TestCase):
    def store_game(self, store, match_id, items_with_times):
        match, timeline = build_match(25, match_id=match_id)
        p = next(q for q in match["info"]["participants"] if q["participantId"] == 9)
        p["championName"] = "Draven"
        for slot, (item_id, _) in enumerate(items_with_times):
            p[f"item{slot}"] = item_id
        for item_id, t in items_with_times:
            timeline["info"]["frames"][int(t // 60) + 1]["events"].append(
                {"type": "ITEM_PURCHASED", "timestamp": int(t * 1000), "participantId": 9, "itemId": item_id})
        store.save_match(match, timeline)

    def test_modal_build_and_order(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        for n in range(4):
            second = 3094 if n < 3 else 3072
            self.store_game(store, f"NA1_{n}", [(3006, 300), (3031, 600), (second, 900), (1038, 1000)])

        class Layer:
            pass
        layer = Layer()
        layer.store = store
        entry = RosterEntry("puuid-9", "p#NA1", 200, "Draven")
        prediction = predict_build(layer, ITEMS, PlayerHistory(entry, [], [f"NA1_{n}" for n in range(4)]))
        self.assertEqual(prediction["games"], 4)
        self.assertEqual(prediction["first_item"], {"item": "Infinity Edge", "rate": 1.0})
        self.assertEqual([i["item"] for i in prediction["modal_build"]][:2], ["Infinity Edge", "Rapid Firecannon"])
        self.assertEqual(prediction["boots"]["item"], "Berserker's Greaves")
        self.assertEqual(prediction["item_spikes_s"], [600, 900])


class RosterTests(unittest.TestCase):
    def test_replay_roster_splits_teams(self):
        match, _ = build_match(20)
        roster = from_match(match, "puuid-2")
        self.assertEqual(roster.my_team, 100)
        self.assertEqual({p.puuid for p in roster.enemies()}, {f"puuid-{i}" for i in range(6, 11)})


if __name__ == "__main__":
    unittest.main()
