"""Champion kits for the v1 champion subset.

Ability numbers are read from Meraki by attribute name, so they follow patches. This file only describes the
mechanics: which values hit, when they hit, what damage type they are, and each champion's special rules.
"""
from dataclasses import dataclass, field
from typing import Callable

from .stats import by_level


@dataclass
class HitSpec:
    attr: str
    dtype: str
    effect: int | None = None
    count: int | Callable = 1
    interval: float = 0.0
    delay: float = 0.0
    scale: float = 1.0
    spread_over: float | None = None  # spread a variable hit count evenly across this many seconds

    def timing(self, me):
        count = self.count(me) if callable(self.count) else self.count
        interval = self.spread_over / count if self.spread_over else self.interval
        return count, interval


@dataclass
class AbilitySpec:
    key: str
    cast_time: float = 0.25
    hits: list[HitSpec] = field(default_factory=list)
    empower_attack: HitSpec | None = None
    shield: HitSpec | None = None
    assumption: str = ""


class Kit:
    name = ""
    abilities: dict[str, AbilitySpec] = {}

    def damage_type(self, sim, me, target, key, hit, t):
        return hit.dtype

    def on_cast(self, sim, me, key, t):
        pass

    def on_ability_hit(self, sim, me, target, key, t):
        pass

    def on_attack_hit(self, sim, me, target, t):
        pass


class Velkoz(Kit):
    name = "Velkoz"
    abilities = {
        "Q": AbilitySpec("Q", 0.25, [HitSpec("Magic Damage", "magic", 0, delay=0.35)]),
        "W": AbilitySpec("W", 0.25, [HitSpec("Magic Damage", "magic", 0, delay=0.1),
                                     HitSpec("Magic Damage", "magic", 1, delay=0.35)]),
        "E": AbilitySpec("E", 0.25, [HitSpec("Magic Damage", "magic", 0, delay=0.5)]),
        "R": AbilitySpec("R", 2.3, [HitSpec("Damage Per Tick", "magic", 2, count=13, interval=2.3 / 13)],
                         assumption="R: all 13 ticks hit"),
    }
    # Deconstruction: 3 ability stacks -> 35-180 (by level) + 60% AP true damage, and the target becomes Researched.
    PASSIVE = (35, 180, 0.60, 7.0)

    def damage_type(self, sim, me, target, key, hit, t):
        # TODO: in game R ticks also apply Deconstruction stacks over the channel; only the Researched true-damage
        #  conversion is modeled here.
        if key == "R" and me.state.get("researched_until", -1) >= t:
            return "true"
        return hit.dtype

    def on_ability_hit(self, sim, me, target, key, t):
        if key == "R":
            return
        lo, hi, ap_ratio, duration = self.PASSIVE
        if me.state.get("vk_expire", -1) < t:
            me.state["vk_stacks"] = 0
        me.state["vk_stacks"] = me.state.get("vk_stacks", 0) + 1
        me.state["vk_expire"] = t + duration
        if me.state["vk_stacks"] >= 3:
            me.state["vk_stacks"] = 0
            me.state["researched_until"] = t + duration
            sim.deal(me, target, by_level(lo, hi, me.stats.level) + ap_ratio * me.ap(t), "true", t, "proc",
                     "Deconstruction")


class Lillia(Kit):
    name = "Lillia"
    abilities = {
        "Q": AbilitySpec("Q", 0.25, [HitSpec("Magic Damage", "magic", 2), HitSpec("Magic Damage", "true", 2)],
                         assumption="Q: outer edge hit (magic + equal true damage)"),
        "W": AbilitySpec("W", 0.25, [HitSpec("Increased Damage", "magic", 0, delay=0.75)],
                         assumption="W: center hit (increased damage)"),
        "E": AbilitySpec("E", 0.4, [HitSpec("Magic Damage", "magic", 0, delay=0.6)]),
        "R": AbilitySpec("R", 0.4, [HitSpec("Magic Damage", "magic", 1, delay=1.8)],
                         assumption="R: target sleeps and is woken by the next hit"),
    }
    # Dream Dust: 5% (+1.25% per 100 AP) target max HP magic over 3s; heals 6-90 (by level) + 30% AP over the burn.
    BURN = (0.05, 0.0125, 3.0)
    HEAL = (6, 90, 0.30)

    def on_ability_hit(self, sim, me, target, key, t):
        pct, per_100_ap, duration = self.BURN
        total = (pct + per_100_ap * me.ap(t) / 100) * target.stats.max_hp
        lo, hi, ap_ratio = self.HEAL
        heal = by_level(lo, hi, me.stats.level) + ap_ratio * me.ap(t)
        sim.apply_burn(me, target, t, "Dream Dust", total, duration, 0.5, "magic", heal_total=heal)


class Karthus(Kit):
    name = "Karthus"
    abilities = {
        "Q": AbilitySpec("Q", 0.25, [HitSpec("Enhanced Damage", "magic", 0, delay=0.6)],
                         assumption="Q: isolated target (enhanced damage)"),
        "E": AbilitySpec("E", 0.0, [HitSpec("Damage Per Second", "magic", 1, count=10, interval=0.5, delay=0.5,
                                            scale=0.5)],
                         assumption="E: Defile stays on for 5 seconds"),
        "R": AbilitySpec("R", 3.0, [HitSpec("Magic Damage", "magic", 0, delay=3.0)]),
    }
    # TODO: Death Defied (zombie form after dying) isn't modeled.


class Garen(Kit):
    name = "Garen"
    abilities = {
        "Q": AbilitySpec("Q", 0.0, empower_attack=HitSpec("Bonus Physical Damage", "physical", 1)),
        "W": AbilitySpec("W", 0.0, shield=HitSpec("Shield Strength", "shield", 2)),
        "E": AbilitySpec("E", 3.0, [HitSpec("Physical Damage Per Spin", "physical", 0,
                                            count=lambda me: 7 + int(me.stats.bonus_attack_speed / 0.25),
                                            spread_over=3.0)],
                         assumption="E: every spin hits; spin crits not modeled"),
        "R": AbilitySpec("R", 0.435, [HitSpec("True Damage", "true", 0)]),
    }


class Vayne(Kit):
    name = "Vayne"
    abilities = {
        "Q": AbilitySpec("Q", 0.3, empower_attack=HitSpec("Bonus Physical Damage", "physical", 0)),
        "E": AbilitySpec("E", 0.25, [HitSpec("Physical Damage", "physical", 0, delay=0.25)],
                         assumption="E: no wall stun"),
        "R": AbilitySpec("R", 0.0),
    }

    def on_cast(self, sim, me, key, t):
        if key == "R":
            rank = me.ranks.get("R", 0)
            bonus = sim.leveling_value(me, "R", "Bonus Attack Damage", 0, rank)
            duration = sim.leveling_value(me, "R", "Effect Duration", 0, rank)
            me.temp_bonus_ad, me.temp_bonus_ad_until = bonus, t + duration

    def _silver_bolts(self, sim, me, target, t):
        stacks = me.state.get("w_stacks", 0) + 1
        if stacks < 3:
            me.state["w_stacks"] = stacks
            return
        me.state["w_stacks"] = 0
        rank = me.ranks.get("W", 0)
        if rank == 0:
            return
        pct = sim.leveling_value(me, "W", "Bonus True Damage", 1, rank, target=target)
        minimum = sim.leveling_value(me, "W", "Minimum Bonus Damage", 1, rank)
        sim.deal(me, target, max(pct, minimum), "true", t, "proc", "Silver Bolts")

    def on_attack_hit(self, sim, me, target, t):
        self._silver_bolts(sim, me, target, t)

    def on_ability_hit(self, sim, me, target, key, t):
        if key == "E":
            self._silver_bolts(sim, me, target, t)


KITS = {k.name: k for k in (Velkoz, Lillia, Karthus, Garen, Vayne)}
