import heapq
import itertools

from . import effects as fx
from .effects import Runes
from .kits import Kit
from .stats import Stats, by_level

DAMAGE_TYPES = ("physical", "magic", "true")


def resist_multiplier(resist):
    return 100 / (100 + resist) if resist >= 0 else 2 - 100 / (100 - resist)


def pick_value(values, rank, level):
    if len(values) == 18:
        return values[level - 1]
    if len(set(values)) == 1:
        return values[0]
    return values[min(max(rank, 1), len(values)) - 1]


class Combatant:
    def __init__(self, label, stats: Stats, *, kit=None, abilities=None, ranks=None, rotation=(), items=(),
                 runes=None, ranged=False, adaptive="magic", windup=0.3):
        self.label = label
        self.stats = stats
        self.kit = kit or Kit()
        self.abilities = abilities or {}
        self.ranks = ranks or {}
        self.rotation = list(rotation)
        self.items = list(items)
        self.item_keys = {i.key for i in self.items}
        self.execute_items = [i for i in self.items if i.execute_amp]
        self.spellblade = next((k for k in fx.SPELLBLADE_PRIORITY if k in self.item_keys), None)
        self.runes = runes or Runes()
        self.ranged = ranged
        self.adaptive = adaptive
        self.windup = windup
        self.hp = stats.max_hp
        self.shield = 0.0
        self.dead_at = None
        self.opponent = None
        self.state = {}
        self.empowered = None
        self.temp_bonus_ad = 0.0
        self.temp_bonus_ad_until = -1.0
        self.gw_until = -1.0
        self.spellblade_armed_until = -1.0
        self.spellblade_ready_at = 0.0
        self.totals = {**{k: 0.0 for k in DAMAGE_TYPES}, "healing": 0.0, "shielding": 0.0, "taken": 0.0,
                       "absorbed": 0.0}

    def has(self, key):
        return key in self.item_keys

    def alive(self):
        return self.dead_at is None

    def hp_pct(self):
        return self.hp / self.stats.max_hp

    def adaptive_force(self, t):
        force = 0.0
        if self.runes.keystone == "Conqueror" and self.state.get("conq_until", -1) >= t:
            lo, hi = fx.CONQUEROR[0], fx.CONQUEROR[1]
            force += self.state.get("conq_stacks", 0) * by_level(lo, hi, self.stats.level)
        if "Absolute Focus" in self.runes.minor and self.hp_pct() > fx.ABSOLUTE_FOCUS[2]:
            force += by_level(fx.ABSOLUTE_FOCUS[0], fx.ABSOLUTE_FOCUS[1], self.stats.level)
        return force

    def ad(self, t):
        extra = self.temp_bonus_ad if t <= self.temp_bonus_ad_until else 0.0
        adaptive = 0.6 * self.adaptive_force(t) if self.adaptive == "physical" else 0.0
        return self.stats.ad + extra + adaptive

    def bonus_ad(self, t):
        return self.ad(t) - self.stats.base_ad

    def ap(self, t):
        adaptive = self.adaptive_force(t) if self.adaptive == "magic" else 0.0
        return (self.stats.ap_raw + adaptive) * (1 + self.stats.ap_amp)


class Sim:
    """Runs both combatants' rotations on one clock. Each side's hits change the other's HP, which affects
    execute thresholds, %current-HP damage and so on. The simulation stops at the window end or on a kill."""

    def __init__(self, attacker: Combatant, target: Combatant, window=None):
        self.attacker, self.target = attacker, target
        attacker.opponent, target.opponent = target, attacker
        self.window = window
        self.log = []
        self.end = 0.0
        self._queue = []
        self._seq = itertools.count()

    def at(self, t, fn, *args):
        heapq.heappush(self._queue, (t, next(self._seq), fn, args))

    def run(self):
        for c in (self.attacker, self.target):
            self._schedule(c)
        while self._queue:
            t, _, fn, args = heapq.heappop(self._queue)
            if self.window is not None and t > self.window:
                break
            if not (self.attacker.alive() and self.target.alive()):
                break
            self.end = max(self.end, t)
            fn(t, *args)
        return self.result()

    # --- ability data -------------------------------------------------------------------------------------

    def _unit(self, unit, c, target, t):
        u = unit.strip()
        table = {
            "": 1.0,
            "seconds": 1.0,
            "% AP": c.ap(t) / 100,
            "% AD": c.ad(t) / 100,
            "% bonus AD": c.bonus_ad(t) / 100,
            "% bonus health": c.stats.bonus_hp / 100,
            "% maximum health": c.stats.max_hp / 100,
            "% of target's maximum health": target.stats.max_hp / 100,
            "% of target's missing health": (target.stats.max_hp - target.hp) / 100,
            "% of target's current health": target.hp / 100,
        }
        if u not in table:
            raise ValueError(f"{c.kit.name}: unsupported ability scaling unit {unit!r}")
        return table[u]

    def leveling_value(self, c, key, attr, effect, rank, target=None, t=0.0):
        target = target or c.opponent
        ability = c.abilities[key][0]
        effects = ability["effects"] if effect is None else [ability["effects"][effect]]
        for eff in effects:
            for lv in eff["leveling"]:
                if lv["attribute"] == attr:
                    return sum(pick_value(m["values"], rank, c.stats.level) * self._unit(m["units"][0], c, target, t)
                               for m in lv["modifiers"])
        raise KeyError(f"{c.kit.name} {key}: no {attr!r} value in the ability data")

    def cooldown(self, c, key, rank):
        cd = c.abilities[key][0].get("cooldown")
        if not cd:
            return 0.0
        return pick_value(cd["modifiers"][0]["values"], rank, c.stats.level) * 100 / (100 + c.stats.haste)

    # --- scheduling --------------------------------------------------------------------------------------

    def _schedule(self, c):
        t = 0.0
        ready = {}
        for aid, token in enumerate(c.rotation):
            token = token.upper()
            if token in ("AA", "A"):
                if not c.stats.attack_speed:
                    raise ValueError(f"{c.label} can't attack")
                period = 1 / c.stats.attack_speed
                self.at(t + period * c.windup, self._attack_hit, c, aid)
                t += period
                continue
            spec = c.kit.abilities.get(token)
            if spec is None:
                raise ValueError(f"{c.label} can't use {token!r}; options: AA, {', '.join(c.kit.abilities)}")
            rank = c.ranks.get(token, 0)
            if rank == 0:
                raise ValueError(f"{c.label} has no points in {token} at level {c.stats.level}")
            start = max(t, ready.get(token, 0.0))
            self.at(start, self._cast, c, spec, aid)
            ready[token] = start + self.cooldown(c, token, rank)
            t = start + spec.cast_time

    def _cast(self, t, c, spec, aid):
        if not c.alive():
            return
        self._log(t, c, None, f"casts {spec.key}", None, 0)
        c.kit.on_cast(self, c, spec.key, t)
        if c.spellblade:
            c.spellblade_armed_until = t + fx.SPELLBLADE_WINDOW
        if spec.empower_attack:
            c.empowered = (spec.key, spec.empower_attack)
        if spec.shield:
            amount = self.leveling_value(c, spec.key, spec.shield.attr, spec.shield.effect, c.ranks[spec.key], t=t)
            self.add_shield(c, amount, t, f"{spec.key} shield")
        for hit in spec.hits:
            count, interval = hit.timing(c)
            for i in range(count):
                self.at(t + hit.delay + i * interval, self._ability_hit, c, spec.key, hit, aid)

    # --- hits --------------------------------------------------------------------------------------------

    def _ability_hit(self, t, c, key, hit, aid):
        target = c.opponent
        raw = self.leveling_value(c, key, hit.attr, hit.effect, c.ranks[key], target, t) * hit.scale
        dtype = c.kit.damage_type(self, c, target, key, hit, t)
        self.deal(c, target, raw, dtype, t, "ability", key)
        c.kit.on_ability_hit(self, c, target, key, t)
        if c.has("liandrystorment"):
            self.apply_burn(c, target, t, "Liandry's Torment", fx.LIANDRY_BURN * target.stats.max_hp, 3.0, 0.5,
                            "magic")
        if c.runes.keystone == "Arcane Comet" and t >= c.state.get("comet_ready", 0.0):
            c.state["comet_ready"] = t + by_level(20, 8, c.stats.level)
            lo, hi, bad, ap = fx.ARCANE_COMET
            amp = fx.COMET_DEFAULT_RANGE_AMP if c.runes.comet_range_amp is None else c.runes.comet_range_amp
            dmg = (by_level(lo, hi, c.stats.level) + bad * c.bonus_ad(t) + ap * c.ap(t)) * (1 + amp)
            self.at(t + 1.0, lambda tt: self.deal(c, target, dmg, self._adaptive_type(c), tt, "proc", "Arcane Comet"))
        self._after_hit(c, target, t, aid, is_attack=False)

    def _attack_hit(self, t, c, aid):
        if not c.alive():
            return
        target = c.opponent
        crit_reduction = fx.RANDUINS_OMEN if target.has("randuinsomen") else 0.0
        expected_crit = c.stats.crit * (c.stats.crit_damage - 1) * (1 - crit_reduction)
        self.deal(c, target, c.ad(t) * (1 + expected_crit), "physical", t, "attack", "AA")
        if c.empowered:
            key, hit = c.empowered
            c.empowered = None
            amount = self.leveling_value(c, key, hit.attr, hit.effect, c.ranks[key], target, t)
            self.deal(c, target, amount, hit.dtype, t, "onhit", f"{key} empowered")
        if c.spellblade and c.spellblade_ready_at <= t <= c.spellblade_armed_until:
            dtype, ad_ratio, ap_ratio = fx.SPELLBLADE[c.spellblade]
            self.deal(c, target, ad_ratio * c.stats.base_ad + ap_ratio * c.ap(t), dtype, t, "onhit", "Spellblade")
            c.spellblade_armed_until = -1.0
            c.spellblade_ready_at = t + fx.SPELLBLADE_CD
        if c.has("nashorstooth"):
            flat, ratio = fx.NASHORS_TOOTH
            self.deal(c, target, flat + ratio * c.ap(t), "magic", t, "onhit", "Nashor's Tooth")
        if c.has("witsend"):
            self.deal(c, target, fx.WITS_END, "magic", t, "onhit", "Wit's End")
        if c.has("bladeoftheruinedking"):
            pct = fx.BOTRK_CURRENT_HP["ranged" if c.ranged else "melee"]
            self.deal(c, target, pct * target.hp, "physical", t, "onhit", "Ruined King")
        if c.has("krakenslayer"):
            c.state["kraken"] = c.state.get("kraken", 0) + 1
            if c.state["kraken"] % 3 == 0:
                lo, hi = fx.KRAKEN_SLAYER
                dmg = lo + (hi - lo) * min(max(c.stats.level - 9, 0), 10) / 10
                self.deal(c, target, dmg * (0.8 if c.ranged else 1.0), "physical", t, "onhit", "Kraken Slayer")
        c.kit.on_attack_hit(self, c, target, t)
        if target.item_keys & fx.GW_WHEN_ATTACKED:
            c.gw_until = t + fx.GW_DURATION
        if target.has("thornmail"):
            flat, ratio = fx.THORNMAIL
            self.deal(target, c, flat + ratio * target.stats.bonus_armor, "magic", t, "proc", "Thornmail")
        self._after_hit(c, target, t, aid, is_attack=True)

    def _adaptive_type(self, c):
        return "physical" if c.adaptive == "physical" else "magic"

    def _after_hit(self, c, target, t, aid, is_attack):
        """Keystone triggers; they count distinct attacks/casts (aid), so multi-hit abilities count once."""
        if not target.alive():
            return
        level = c.stats.level
        keystone = c.runes.keystone
        if keystone == "Electrocute" and t >= c.state.get("electrocute_ready", 0.0):
            recent = {a: s for a, s in c.state.get("elec", {}).items() if s >= t - 3.0}
            recent[aid] = t
            c.state["elec"] = recent
            if len(recent) >= 3:
                lo, hi, bad, ap, cd = fx.ELECTROCUTE
                dmg = by_level(lo, hi, level) + bad * c.bonus_ad(t) + ap * c.ap(t)
                c.state["elec"] = {}
                c.state["electrocute_ready"] = t + cd
                self.deal(c, target, dmg, self._adaptive_type(c), t, "proc", "Electrocute")
        elif keystone == "Press the Attack" and is_attack and not c.state.get("pta_exposed"):
            c.state["pta"] = c.state.get("pta", 0) + 1
            if c.state["pta"] >= 3:
                lo, hi, _ = fx.PRESS_THE_ATTACK
                self.deal(c, target, by_level(lo, hi, level), self._adaptive_type(c), t, "proc", "Press the Attack")
                c.state["pta_exposed"] = True
        elif keystone == "Conqueror" and aid not in c.state.setdefault("conq_seen", set()):
            c.state["conq_seen"].add(aid)
            gain = 1 if (is_attack and c.ranged) else 2
            if c.state.get("conq_until", -1) < t:
                c.state["conq_stacks"] = 0
            c.state["conq_stacks"] = min(fx.CONQUEROR[2], c.state.get("conq_stacks", 0) + gain)
            c.state["conq_until"] = t + fx.CONQUEROR[3]
        elif keystone == "Dark Harvest" and t >= c.state.get("dh_ready", 0.0) and target.hp_pct() < fx.DARK_HARVEST[5]:
            base, per_soul, bad, ap, cd, _ = fx.DARK_HARVEST
            dmg = base + per_soul * c.runes.dark_harvest_souls + bad * c.bonus_ad(t) + ap * c.ap(t)
            c.state["dh_ready"] = t + cd
            self.deal(c, target, dmg, self._adaptive_type(c), t, "proc", "Dark Harvest")

    # --- damage, healing, shields ---------------------------------------------------------------------------

    def effective_armor(self, src, dst, t):
        armor = dst.stats.armor
        if armor > 0 and dst.state.get("cleaver_until", -1) >= t:
            armor *= 1 - fx.BLACK_CLEAVER[0] * dst.state.get("cleaver_stacks", 0)
        if armor > 0:
            armor = max(0.0, armor * (1 - src.stats.armor_pen) - src.stats.lethality)
        return armor

    def effective_mr(self, src, dst):
        mr = dst.stats.mr
        if mr > 0:
            mr = max(0.0, mr * (1 - src.stats.magic_pen_pct) - src.stats.magic_pen_flat)
        return mr

    def _amplifier(self, src, dst, dtype, t):
        mult = 1.0
        if src.state.get("pta_exposed"):
            mult *= 1 + fx.PRESS_THE_ATTACK[2]
        hp_pct = dst.hp_pct()
        if "Coup de Grace" in src.runes.minor and hp_pct < fx.COUP_DE_GRACE[1]:
            mult *= 1 + fx.COUP_DE_GRACE[0]
        if "Cut Down" in src.runes.minor and hp_pct > fx.CUT_DOWN[1]:
            mult *= 1 + fx.CUT_DOWN[0]
        if "Last Stand" in src.runes.minor and src.hp_pct() < fx.LAST_STAND[2]:
            lo, hi, start, full = fx.LAST_STAND
            mult *= 1 + lo + (hi - lo) * min(1.0, (start - src.hp_pct()) / (start - full))
        if src.has("liandrystorment") and "combat_start" in src.state:
            per, cap = fx.LIANDRY_SUFFERING
            mult *= 1 + per * min(cap, int(t - src.state["combat_start"]))
        for item in src.execute_items:
            if dtype in ("magic", "true") and hp_pct < item.execute_threshold:
                mult *= 1 + item.execute_amp
        return mult

    def deal(self, src, dst, amount, dtype, t, kind, label):
        if amount <= 0 or not dst.alive():
            return 0.0
        amount *= self._amplifier(src, dst, dtype, t)
        if dtype == "physical":
            amount *= resist_multiplier(self.effective_armor(src, dst, t))
        elif dtype == "magic":
            amount *= resist_multiplier(self.effective_mr(src, dst))
        if kind == "attack" and dst.has("platedsteelcaps"):
            amount *= 1 - fx.PLATED_STEELCAPS
        absorbed = min(dst.shield, amount)
        dst.shield -= absorbed
        dst.hp -= amount - absorbed
        src.totals[dtype] += amount
        dst.totals["taken"] += amount
        dst.totals["absorbed"] += absorbed
        for c in (src, dst):
            c.state.setdefault("combat_start", t)

        if dtype == "physical" and src.has("blackcleaver"):
            per, cap, duration = fx.BLACK_CLEAVER
            stacks = dst.state.get("cleaver_stacks", 0) if dst.state.get("cleaver_until", -1) >= t else 0
            dst.state["cleaver_stacks"] = min(cap, stacks + 1)
            dst.state["cleaver_until"] = t + duration
        if (dtype == "magic" and src.item_keys & fx.GW_ON_MAGIC) or (
                dtype == "physical" and src.item_keys & fx.GW_ON_PHYSICAL):
            dst.gw_until = t + fx.GW_DURATION

        sustain = amount * src.stats.omnivamp
        if kind in ("attack", "onhit"):
            sustain += amount * src.stats.lifesteal
        if src.runes.keystone == "Conqueror" and src.state.get("conq_until", -1) >= t \
                and src.state.get("conq_stacks", 0) >= fx.CONQUEROR[2]:
            sustain += amount * (fx.CONQUEROR[5] if src.ranged else fx.CONQUEROR[4])
        if sustain:
            self.heal(src, sustain, t)

        if dst.hp <= 0:
            dst.hp = 0.0
            dst.dead_at = t
        self._log(t, src, dst, label, dtype, amount)
        return amount

    def heal(self, c, amount, t):
        if not c.alive():
            return
        if c.gw_until >= t:
            amount *= 1 - fx.GRIEVOUS_WOUNDS
        if c.has("spiritvisage"):
            amount *= 1 + fx.SPIRIT_VISAGE
        actual = min(amount, c.stats.max_hp - c.hp)
        c.hp += actual
        c.totals["healing"] += actual

    def add_shield(self, c, amount, t, label):
        # TODO: shield duration/decay isn't modeled; shields last for the rest of the trade.
        if c.has("spiritvisage"):
            amount *= 1 + fx.SPIRIT_VISAGE
        c.shield += amount
        c.totals["shielding"] += amount
        self._log(t, c, c, label, "shield", amount)

    def apply_burn(self, src, dst, t, name, total, duration, interval, dtype, heal_total=0.0):
        """Damage over time; re-applying restarts it (the old ticks are dropped)."""
        gen = dst.state.get(("burn", name), 0) + 1
        dst.state[("burn", name)] = gen
        ticks = round(duration / interval)
        for i in range(1, ticks + 1):
            self.at(t + i * interval, self._burn_tick, src, dst, name, gen, total / ticks, dtype, heal_total / ticks)

    def _burn_tick(self, t, src, dst, name, gen, amount, dtype, heal):
        if dst.state.get(("burn", name)) != gen:
            return
        self.deal(src, dst, amount, dtype, t, "dot", name)
        if heal:
            self.heal(src, heal, t)

    # --- output ------------------------------------------------------------------------------------------

    def _log(self, t, src, dst, label, dtype, amount):
        self.log.append({"t": round(t, 2), "source": src.label, "target": dst.label if dst else None,
                         "what": label, "type": dtype, "amount": round(amount, 1)})

    def result(self):
        def side(c):
            dealt = {k: round(c.totals[k]) for k in DAMAGE_TYPES}
            return {
                "name": c.label,
                "damage_dealt": sum(dealt.values()),
                "by_type": dealt,
                "healing": round(c.totals["healing"]),
                "shielding": round(c.totals["shielding"]),
                "damage_taken": round(c.totals["taken"]),
                "hp_start": round(c.stats.max_hp),
                "hp_end": round(c.hp),
                "died_at": round(c.dead_at, 2) if c.dead_at is not None else None,
            }

        a, b = side(self.attacker), side(self.target)
        lost_a = self.attacker.totals["taken"] - self.attacker.totals["absorbed"] - self.attacker.totals["healing"]
        lost_b = self.target.totals["taken"] - self.target.totals["absorbed"] - self.target.totals["healing"]
        return {"duration": round(self.end, 2), "attacker": a, "target": b, "net_trade": round(lost_b - lost_a),
                "log": self.log}
