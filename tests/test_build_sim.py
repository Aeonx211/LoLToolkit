import unittest

from build_sim.data import Item, parse_item_stats
from build_sim.effects import Runes
from build_sim.engine import Combatant, Sim, resist_multiplier
from build_sim.kits import AbilitySpec, HitSpec, Kit
from build_sim.scenario import ranks_from_order
from build_sim.stats import Stats, dummy_stats


def ability_data(flat=100, ap_pct=50, cooldown=0):
    return {"Q": [{
        "effects": [{"leveling": [{"attribute": "Magic Damage", "modifiers": [
            {"values": [flat] * 5, "units": [""] * 5},
            {"values": [ap_pct] * 5, "units": ["% AP"] * 5},
        ]}]}],
        "cooldown": {"modifiers": [{"values": [cooldown] * 5}]},
    }]}


class NukeKit(Kit):
    name = "Test"
    abilities = {"Q": AbilitySpec("Q", 0.25, [HitSpec("Magic Damage", "magic", 0)])}


def caster(ap=100, items=(), runes=None, rotation=("Q",), cooldown=0, **stat_overrides):
    stats = Stats(level=11, base_hp=2000, max_hp=2000, armor=50, bonus_armor=0, mr=50, base_ad=60, bonus_ad=0,
                  ap_raw=ap, ap_amp=0, attack_speed=0.7, bonus_attack_speed=0, **stat_overrides)
    return Combatant("Caster", stats, kit=NukeKit(), abilities=ability_data(cooldown=cooldown), ranks={"Q": 5},
                     rotation=rotation, items=items, runes=runes)


def item(key, **kwargs):
    return Item(id="1", name=key, key=key, cost=3000, stats={}, description="", **kwargs)


class MathTests(unittest.TestCase):
    def test_resist_multiplier(self):
        self.assertAlmostEqual(resist_multiplier(100), 0.5)
        self.assertAlmostEqual(resist_multiplier(0), 1.0)
        self.assertAlmostEqual(resist_multiplier(-50), 2 - 100 / 150)

    def test_parse_item_stats(self):
        desc = ("<mainText><stats><attention>55</attention> Attack Damage<br><attention>18</attention> Lethality"
                "<br><attention>4%</attention> Move Speed</stats><br><br><passive>Haunt</passive></mainText>")
        self.assertEqual(parse_item_stats(desc), {"ad": 55, "lethality": 18})
        void = "<mainText><stats><attention>95</attention> Ability Power<br><attention>40%</attention> Magic Penetration</stats></mainText>"
        self.assertEqual(parse_item_stats(void), {"ap": 95, "magic_pen_pct": 0.4})

    def test_ranks_from_order(self):
        self.assertEqual(ranks_from_order("QEW", 11), {"Q": 5, "W": 1, "E": 3, "R": 2})
        self.assertEqual(ranks_from_order("QWE", 18), {"Q": 5, "W": 5, "E": 5, "R": 3})
        with self.assertRaises(ValueError):
            ranks_from_order("QQE", 5)


class EngineTests(unittest.TestCase):
    def run_sim(self, attacker, target=None, window=None):
        target = target or Combatant("Dummy", dummy_stats(3000, 60, 50))
        return Sim(attacker, target, window).run()

    def test_magic_damage_with_penetration(self):
        r = self.run_sim(caster(magic_pen_pct=0.4))
        # (100 + 50% of 100 AP) vs 50 MR reduced 40% -> 30 MR
        self.assertEqual(r["attacker"]["by_type"]["magic"], round(150 * 100 / 130))

    def test_cooldowns_respect_ability_haste(self):
        slow = self.run_sim(caster(rotation=("Q", "Q"), cooldown=10))
        fast = self.run_sim(caster(rotation=("Q", "Q"), cooldown=10, haste=100))
        self.assertEqual(slow["duration"], 10.0)
        self.assertEqual(fast["duration"], 5.0)

    def test_electrocute_needs_three_separate_casts(self):
        two = self.run_sim(caster(rotation=("Q", "Q"), runes=Runes(keystone="Electrocute")))
        three = self.run_sim(caster(rotation=("Q", "Q", "Q"), runes=Runes(keystone="Electrocute")))
        self.assertFalse(any(e["what"] == "Electrocute" for e in two["log"]))
        self.assertEqual(sum(e["what"] == "Electrocute" for e in three["log"]), 1)

    def test_execute_amp_below_threshold(self):
        shadowflame = item("shadowflame", execute_threshold=0.4, execute_amp=0.2)
        target = Combatant("Dummy", dummy_stats(1000, 0, 0))
        target.hp = 300
        r = self.run_sim(caster(items=[shadowflame]), target)
        self.assertEqual(r["attacker"]["by_type"]["magic"], 150 * 1.2)

    def test_kill_ends_simulation(self):
        r = self.run_sim(caster(ap=1000, rotation=("Q", "Q", "Q")), Combatant("Dummy", dummy_stats(500, 0, 0)))
        self.assertEqual(r["target"]["hp_end"], 0)
        self.assertEqual(r["target"]["died_at"], 0.0)
        self.assertEqual(sum(1 for e in r["log"] if e["what"] == "Q"), 1)

    def test_grievous_wounds_cuts_healing(self):
        healthy = caster(omnivamp=0.5)
        healthy.hp = 1000
        wounded = caster(omnivamp=0.5)
        wounded.hp = 1000
        wounded.gw_until = 99
        a = self.run_sim(healthy)
        b = self.run_sim(wounded)
        self.assertAlmostEqual(b["attacker"]["healing"], round(a["attacker"]["healing"] * 0.6), delta=1)


if __name__ == "__main__":
    unittest.main()
