import unittest

from data_layer import Store
from live_advisor.build_predict import predict_build
from live_advisor.counters import counter_itemization
from live_advisor.healing import assess_enemy, classify_champion, classify_item, grievous_wounds
from live_advisor.history import PlayerHistory
from live_advisor.onetrick import champion_pool
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
    def profile(self, physical, magic):
        return {"champion": "X", "damage_per_min": {"physical": physical, "magic": magic, "true": 0}}

    def test_magic_heavy_team_gets_mr_advice(self):
        c = counter_itemization([self.profile(100, 900), self.profile(200, 800)])
        self.assertTrue(c["resist_advice"].startswith("Magic resist"))


def spell(description, tooltip=""):
    return {"description": description, "tooltip": tooltip}


ILLAOI = {"passive": {"description": "Tentacles deal physical damage to enemies hit, and will heal Illaoi if they damage a champion."},
          "spells": [spell("Illaoi smashes down a Tentacle."), spell("Illaoi leaps to her target."),
                     spell("Illaoi rips the spirit from a foe.", "Deals {{ healthpercenttotal }} damage."), spell("Illaoi smashes her idol.")]}
YUUMI = {"passive": {"description": "Yuumi restores health to herself and the next ally she Attaches to."},
         "spells": [spell("Yuumi fires a missile."),
                    spell("Yuumi dashes to a target ally, gains Heal & Shield Power and grants her ally On-Hit healing."),
                    spell("Yuumi shields herself."), spell("Yuumi channels five waves that damage enemies and heal allies.")]}
SORAKA = {"passive": {"description": "Soraka runs faster towards nearby low health allies."},
          "spells": [spell("A star falls. If an enemy champion is hit, Soraka recovers Health."),
                     spell("Soraka sacrifices a portion of her own health to heal another friendly champion."),
                     spell("Creates a zone that silences all enemies inside."),
                     spell("Soraka fills her allies with hope, instantly restoring health to herself and all allied champions.")]}
SYNDRA = {"passive": {"description": "Syndra collects Splinters of Wrath. Executes low health targets."},
          "spells": [spell("Syndra conjures a Dark Sphere."), spell("Syndra hurls the object, slowing enemies."),
                     spell("Syndra knocks enemies back."), spell("Syndra bombards an enemy Champion.")]}
WUKONG = {"passive": {"description": "Wukong gains stacking armor and max health regeneration while fighting champions."},
          "spells": [spell("Wukong's next attack reduces the target's armor."), spell("Wukong becomes Invisible."),
                     spell("Wukong dashes to a targeted enemy."), spell("Wukong spins his staff, knocking up enemies.")]}
BLOODTHIRSTER = {"description": "<stats>80 Attack Damage 15% Life Steal</stats> Convert excess healing from your Lifesteal to a Shield."}
CHEMTECH = {"description": "<stats>35 Ability Power 10% Heal and Shield Power</stats> Dealing damage applies 40% Grievous Wounds. "
                           "Grievous Wounds reduces the effectiveness of Healing and Regeneration."}
SPIRIT_VISAGE = {"description": "<stats>400 Health</stats> Boundless Vitality: Heals and Shields on you are increased by 25%."}


class HealingTests(unittest.TestCase):
    def test_kit_scan_finds_heals_and_ignores_the_rest(self):
        self.assertEqual(classify_champion(ILLAOI), {"self": ["P"], "ally": []})
        self.assertEqual(classify_champion(YUUMI), {"self": [], "ally": ["P", "W", "R"]})
        self.assertEqual(classify_champion(SORAKA), {"self": ["Q"], "ally": ["W", "R"]})
        self.assertEqual(classify_champion(SYNDRA), {"self": [], "ally": []})
        self.assertEqual(classify_champion(WUKONG), {"self": [], "ally": []})

    def test_item_scan_ignores_anti_heal_and_heal_amps(self):
        self.assertEqual(classify_item(BLOODTHIRSTER), "self")
        self.assertIsNone(classify_item(CHEMTECH))
        self.assertIsNone(classify_item(SPIRIT_VISAGE))

    def assess(self, champion, kit, **kwargs):
        return assess_enemy(champion, classify_champion(kit), {}, {}, **kwargs)

    def test_one_self_healer_is_not_enough(self):
        self.assertEqual(grievous_wounds([self.assess("Illaoi", ILLAOI)])["urgency"], "low")

    def test_two_minor_sources_add_up(self):
        gw = grievous_wounds([self.assess("Illaoi", ILLAOI), self.assess("Yuumi", YUUMI)])
        self.assertEqual(gw["urgency"], "consider")
        self.assertEqual([s["champion"] for s in gw["sources"]], ["Yuumi", "Illaoi"])

    def test_core_healer_alone_is_high_priority(self):
        gw = grievous_wounds([self.assess("Soraka", SORAKA), self.assess("Syndra", SYNDRA)])
        self.assertEqual(gw["urgency"], "high")
        self.assertEqual([s["champion"] for s in gw["sources"]], ["Soraka"])

    def test_healing_items_add_weight_by_build_rate(self):
        items = {"3072": {"name": "Bloodthirster"}}
        build = {"modal_build": [{"item": "Bloodthirster", "rate": 0.4}]}
        with_item = assess_enemy("Draven", classify_champion(SYNDRA), {"3072": "self"}, items, build)
        self.assertEqual(with_item["score"], 0.06)
        self.assertEqual(with_item["reasons"], ["builds Bloodthirster (40% of games)"])
        self.assertEqual(self.assess("Draven", SYNDRA)["score"], 0)

    def test_early_enemy_moves_the_timing_up(self):
        early = grievous_wounds([self.assess("Soraka", SORAKA, early=True)])
        self.assertEqual(early["timing"], "by your first or second item")
        self.assertEqual(grievous_wounds([self.assess("Soraka", SORAKA)])["timing"], "by your third item")


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


class OneTrickTests(unittest.TestCase):
    class Layer:
        def __init__(self, picks):
            self.picks, self.asked = picks, {}

        def recent_match_ids(self, puuid, count, queue, end_time, priority):
            self.asked = {"count": count, "queue": queue, "end_time": end_time}
            return [f"NA1_{i}" for i in range(len(self.picks))]

        def champion_picked(self, match_id, puuid, priority):
            return self.picks[int(match_id.split("_")[1])]

    def pool(self, picks, playing="Draven"):
        layer = self.Layer(picks)
        entry = RosterEntry("p", "p#NA1", 200, playing)
        return champion_pool(layer, entry, 420, 5_000_000), layer

    def test_fifteen_of_twenty_is_a_one_trick(self):
        pool, layer = self.pool(["Draven"] * 15 + ["Jinx"] * 3 + ["Ashe"] * 2)
        self.assertTrue(pool["one_trick"])
        self.assertTrue(pool["on_it"])
        self.assertEqual((pool["champion"], pool["games"], pool["total"]), ("Draven", 15, 20))
        self.assertEqual(layer.asked, {"count": 20, "queue": 420, "end_time": 4999})

    def test_fourteen_of_twenty_is_not(self):
        self.assertFalse(self.pool(["Draven"] * 14 + ["Jinx"] * 6)[0]["one_trick"])

    def test_short_history_uses_the_same_share_but_needs_a_sample(self):
        self.assertTrue(self.pool(["Draven"] * 9 + ["Jinx"] * 3, playing="Jinx")[0]["one_trick"])
        self.assertFalse(self.pool(["Draven"] * 4)[0]["one_trick"])
        self.assertFalse(self.pool(["Draven"] * 9 + ["Jinx"] * 3, playing="Jinx")[0]["on_it"])

    def test_store_remembers_picks_from_a_match_without_timeline(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        match, _ = build_match(20, match_id="NA1_77")
        store.save_picks(match)
        self.assertEqual(store.get_pick("NA1_77", "puuid-3"), "Champ3")
        self.assertIsNone(store.get_pick("NA1_78", "puuid-3"))


class RosterTests(unittest.TestCase):
    def test_replay_roster_splits_teams(self):
        match, _ = build_match(20)
        roster = from_match(match, "puuid-2")
        self.assertEqual(roster.my_team, 100)
        self.assertEqual({p.puuid for p in roster.enemies()}, {f"puuid-{i}" for i in range(6, 11)})


if __name__ == "__main__":
    unittest.main()
