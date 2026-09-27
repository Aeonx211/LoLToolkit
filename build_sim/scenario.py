from .data import GameData, norm
from .effects import MODELED_ITEMS, SHARDS, Runes
from .engine import Combatant, Sim
from .kits import KITS
from .stats import by_level, champion_stats, dummy_stats

DEFAULT_DUMMY = {"hp": 2500, "armor": 60, "mr": 50}


def ranks_from_order(order, level):
    """Ability ranks at `level` from a max-order like "QEW": R at 6/11/16, the first three levels take one of each."""
    order = [k for k in order.upper() if k in "QWE"]
    if sorted(order) != ["E", "Q", "W"]:
        raise ValueError(f"skill_order must list Q, W and E once each (e.g. 'QEW'), got {order!r}")
    ranks = {"Q": 0, "W": 0, "E": 0, "R": 0}
    for lvl in range(1, level + 1):
        if lvl in (6, 11, 16):
            ranks["R"] += 1
        elif lvl <= 3:
            ranks[order[lvl - 1]] += 1
        else:
            key = next(k for k in order if ranks[k] < 5 and ranks[k] < (lvl + 1) // 2)
            ranks[key] += 1
    return ranks


def build_combatant(data: GameData, spec: dict, label=None):
    if "dummy" in spec:
        d = {**DEFAULT_DUMMY, **(spec["dummy"] or {})}
        return Combatant(label or "Dummy", dummy_stats(d["hp"], d["armor"], d["mr"]))

    key = data.champion_key(spec["champion"])
    if key not in KITS:
        raise ValueError(f"{key} isn't simulated yet; v1 champions: {', '.join(KITS)}")
    meraki = data.meraki(key)
    level = int(spec.get("level", 11))
    if not 1 <= level <= 18:
        raise ValueError("level must be 1-18")
    items = [data.item(name) for name in spec.get("items", [])]
    runes = Runes(**spec.get("runes", {}))
    runes.validate()
    ranks = spec.get("ranks") or ranks_from_order(spec.get("skill_order", "QWE"), level)

    extra, adaptive_force = {}, 0.0
    for shard in runes.shards:
        for stat, value in SHARDS[shard].items():
            if stat == "adaptive_force":
                adaptive_force += value
            elif stat == "hp_by_level":
                extra["hp"] = extra.get("hp", 0) + by_level(*value, level)
            else:
                extra[stat] = extra.get(stat, 0) + value

    item_ad = sum(i.stats.get("ad", 0) for i in items)
    item_ap = sum(i.stats.get("ap", 0) for i in items)
    if item_ad != item_ap:
        adaptive = "physical" if item_ad > item_ap else "magic"
    else:
        adaptive = "physical" if meraki["adaptiveType"] == "PHYSICAL_DAMAGE" else "magic"

    base = data.champion_stats(key)
    stats = champion_stats(base, level, items, extra, adaptive_force, adaptive,
                           as_ratio=meraki["stats"]["attackSpeedRatio"]["flat"])
    windup = min(0.5, max(0.1, meraki["stats"]["attackCastTime"]["flat"] * base["attackspeed"]))
    return Combatant(label or KITS[key].name, stats, kit=KITS[key](), abilities=meraki["abilities"], ranks=ranks,
                     rotation=spec.get("rotation", []), items=items, runes=runes,
                     ranged=meraki["attackType"] == "RANGED", adaptive=adaptive, windup=windup)


def _notes(c: Combatant):
    assumptions = []
    for token in dict.fromkeys(t.upper() for t in c.rotation):
        spec = c.kit.abilities.get(token)
        if spec and spec.assumption:
            assumptions.append(f"{c.label} {spec.assumption}")
    unmodeled = [i.name for i in c.items if i.has_passive and i.key not in MODELED_ITEMS]
    return assumptions, unmodeled


def run_scenario(data: GameData, scenario: dict, attacker=None):
    attacker_spec = attacker or scenario["attacker"]
    target_spec = scenario.get("target") or {"dummy": {}}
    a_label = b_label = None
    if attacker_spec.get("champion") and norm(attacker_spec["champion"]) == norm(target_spec.get("champion", "")):
        a_label, b_label = f"{attacker_spec['champion']} (you)", f"{target_spec['champion']} (enemy)"
    a = build_combatant(data, attacker_spec, a_label)
    b = build_combatant(data, target_spec, b_label)
    result = Sim(a, b, scenario.get("window")).run()
    notes_a, notes_b = _notes(a), _notes(b)
    result["assumptions"] = notes_a[0] + notes_b[0]
    result["unmodeled_passives"] = sorted(set(notes_a[1] + notes_b[1]))
    result["attacker"]["stats"] = _stat_summary(a)
    return result


def _stat_summary(c: Combatant):
    s = c.stats
    return {"level": s.level, "hp": round(s.max_hp), "ad": round(s.ad), "ap": round(s.ap),
            "attack_speed": round(s.attack_speed, 3), "armor": round(s.armor), "mr": round(s.mr),
            "lethality": s.lethality, "armor_pen": s.armor_pen, "magic_pen": [s.magic_pen_flat, s.magic_pen_pct],
            "haste": s.haste, "crit": s.crit, "ranks": c.ranks}


def default_candidates(data: GameData, attacker_spec):
    """Legendary items that fit the build's damage type, as swap candidates."""
    raw = data.dd.items(data.version)
    stat = "ad" if build_combatant(data, attacker_spec).adaptive == "physical" else "ap"
    out = []
    for item in data.items().values():
        info = raw[item.id]
        if info.get("into") or item.cost < 2200 or "Boots" in info.get("tags", []):
            continue
        if item.stats.get(stat, 0) > 0:
            out.append(item.name)
    return sorted(out)


def compare(data: GameData, scenario, build_b):
    a = run_scenario(data, scenario)
    b = run_scenario(data, scenario, attacker={**scenario["attacker"], **build_b})
    return a, b


def breakpoints(data: GameData, scenario, candidates=None, keystones=True):
    """How the result changes when one item (or the keystone) is swapped out."""
    base = run_scenario(data, scenario)
    attacker = scenario["attacker"]
    owned = {norm(i) for i in attacker.get("items", [])}
    candidates = candidates or default_candidates(data, attacker)
    rows = []

    raw = data.dd.items(data.version)

    def record(change, spec, gold=0):
        r = run_scenario(data, scenario, attacker=spec)
        rows.append({
            "change": change,
            "damage": r["attacker"]["damage_dealt"] - base["attacker"]["damage_dealt"],
            "net_trade": r["net_trade"] - base["net_trade"],
            "gold": gold,
            "kills_at": r["target"]["died_at"],
        })

    for slot, current in enumerate(attacker.get("items", [])):
        current_item = data.item(current)
        if "Boots" in raw[current_item.id].get("tags", []):
            continue
        for cand in candidates:
            if norm(cand) in owned:
                continue
            items = list(attacker["items"])
            items[slot] = cand
            record(f"{current} -> {cand}", {**attacker, "items": items}, data.item(cand).cost - current_item.cost)
    if keystones:
        current = attacker.get("runes", {}).get("keystone")
        for ks in ("Electrocute", "Arcane Comet", "Press the Attack", "Conqueror", "Dark Harvest"):
            if ks != current:
                record(f"{current or 'no keystone'} -> {ks}",
                       {**attacker, "runes": {**attacker.get("runes", {}), "keystone": ks}})
    if base["target"]["died_at"] is not None:
        # The fight ends on the kill, so a faster kill can show less total damage; rank by kill time instead.
        rows.sort(key=lambda r: (r["kills_at"] is None, r["kills_at"] or 0, -r["damage"]))
    else:
        rows.sort(key=lambda r: r["damage"], reverse=True)
    return base, rows
