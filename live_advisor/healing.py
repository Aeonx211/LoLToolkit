import re
from concurrent.futures import ThreadPoolExecutor

from data_layer import DataDragon

from .build_predict import is_legendary

# TODO: first-guess weights for the Grievous Wounds call; tune against real games. A champion's healing counts
#  more when it's their identity (CORE_HEALERS), a little per ability that heals, and more again per healing item
#  they usually build. Enemy scores add up, so several small sources can add up to buying it.
KIT_ABILITY_WEIGHT = 0.25
KIT_ABILITY_CAP = 0.6
CORE_HEALER_WEIGHT = 2.0
ITEM_WEIGHT = 0.15
ITEM_CAP = 0.3
GW_CONSIDER = 0.75
GW_HIGH = 1.75

# Champions whose kit is built around healing or life drain; Data Dragon's text can't tell us how much a heal is
# worth, so this list carries that judgement. Keyed by Data Dragon champion id.
CORE_HEALERS = {"Soraka", "Aatrox", "Warwick", "Vladimir", "Sona", "Nami", "DrMundo", "Swain", "Zac"}

SLOTS = ["Q", "W", "E", "R"]

_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")
_TAG = re.compile(r"<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n|<br\s*/?>", re.I)
_HEAL_POWER = re.compile(r"heal(?:ing)?\s*(?:&|and)\s*shield\s*power|heals?\s*(?:&|and)\s*shields?", re.I)
_HEALS = re.compile(
    r"\bheal(?:s|ed|ing)?\b|\blife ?steal\b|\bomnivamp\b|\bspell ?vamp\b"
    r"|\b(?:restor|recover)(?:e|es|ed|ing|s)?\b[^.]{0,40}\bhealth\b|\bhealth\b[^.]{0,20}\b(?:restor|recover)"
    r"|\bdrain\w*[^.]{0,30}\bhealth\b|\bsteal\w*[^.]{0,30}\bhealth\b", re.I)
# Sentences about cutting or boosting healing rather than doing it.
_NOT_A_HEAL = re.compile(
    r"grievous|anti-?heal|reduc\w*\s+(?:\w+\s+){0,3}heal|heal\w*\s+reduc|cannot be healed|prevent\w*\s+(?:\w+\s+)?heal"
    r"|heal\w*[^.]{0,30}\b(?:increased|amplified|effectiveness)", re.I)
_ALLY = re.compile(r"\b(?:ally|allies|allied|teammate|teammates|friendly)\b", re.I)


def _heals(text):
    """(heals_self, heals_allies) from a block of ability or item text."""
    text = _HEAL_POWER.sub("", _PLACEHOLDER.sub("", _TAG.sub(" ", text)))
    self_heal = ally_heal = False
    for sentence in _SENTENCE.split(text):
        if not _HEALS.search(sentence) or _NOT_A_HEAL.search(sentence):
            continue
        if _ALLY.search(sentence):
            ally_heal = True
        else:
            self_heal = True
    return self_heal, ally_heal


def classify_champion(data):
    """Which ability slots (P/Q/W/E/R) heal the champion or their allies, from a Data Dragon champion entry."""
    slots = {"self": [], "ally": []}
    parts = [("P", data["passive"]["description"])]
    parts += [(SLOTS[i], f'{s.get("description", "")}. {s.get("tooltip", "")}') for i, s in enumerate(data["spells"][:4])]
    for slot, text in parts:
        self_heal, ally_heal = _heals(text)
        if self_heal:
            slots["self"].append(slot)
        if ally_heal:
            slots["ally"].append(slot)
    return slots


def classify_item(item):
    """'self' (lifesteal/omnivamp/heals you), 'ally' (heals allies) or None for a Data Dragon item entry."""
    self_heal, ally_heal = _heals(item.get("description", ""))
    return "self" if self_heal else "ally" if ally_heal else None


def champion_heal_kits(dd: DataDragon, progress=None):
    """{champion id: {'self': [slots], 'ally': [slots]}} for every champion, built once per patch."""
    def build(version):
        ids = [c["id"] for c in dd.champions(version).values()]
        if progress:
            progress(f"Reading {len(ids)} champions' abilities for healing (once per patch)")
        with ThreadPoolExecutor(max_workers=8) as pool:
            return dict(zip(ids, pool.map(lambda cid: classify_champion(dd.champion(cid, version)), ids)))
    return dd.derived("heal_kits.json", build)


def item_heal_kinds(dd: DataDragon):
    """{item id: 'self' | 'ally'} for every finished item that heals, built once per patch."""
    def build(version):
        items = dd.items(version)
        return {i: kind for i, item in items.items() if is_legendary(item) and (kind := classify_item(item))}
    return dd.derived("heal_items.json", build)


def _join(slots):
    return ", ".join("passive" if s == "P" else s for s in slots)


def assess_enemy(champion, kit, item_kinds, items, build=None, live_items=(), early=False):
    """How much reason this one enemy gives to buy Grievous Wounds, and why (from their kit and what they build)."""
    kit = kit or {"self": [], "ally": []}
    reasons = []
    if champion in CORE_HEALERS:
        kit_score = CORE_HEALER_WEIGHT
        reasons.append("healing is central to their kit")
    else:
        kit_score = min(KIT_ABILITY_CAP, KIT_ABILITY_WEIGHT * len(set(kit["self"]) | set(kit["ally"])))
    if kit["self"] and champion not in CORE_HEALERS:
        reasons.append(f"heals themselves ({_join(kit['self'])})")
    if kit["ally"] and champion not in CORE_HEALERS:
        reasons.append(f"heals allies ({_join(kit['ally'])})")

    # How often each healing item is expected: the modal build's rates, or 100% for what they already own.
    rates = {}
    healing_names = {items[i]["name"] for i in item_kinds if i in items}  # names, since one item can have several ids
    for entry in (build or {}).get("modal_build", []):
        if entry["item"] in healing_names:
            rates[entry["item"]] = entry["rate"]
    for name in live_items:
        if name in healing_names:
            rates[name] = 1.0
    item_score = min(ITEM_CAP, ITEM_WEIGHT * sum(rates.values()))
    for name, rate in rates.items():
        reasons.append(f"builds {name}" + ("" if rate >= 1 else f" ({round(rate * 100)}% of games)"))

    return {"champion": champion, "score": round(kit_score + item_score, 2), "reasons": reasons, "early": early}


def grievous_wounds(assessments):
    """Team-level Grievous Wounds call from the per-enemy assessments: scores add up across the enemy team."""
    sources = sorted((a for a in assessments if a["score"] > 0), key=lambda a: -a["score"])
    total = round(sum(a["score"] for a in sources), 2)
    urgency = "high" if total >= GW_HIGH else "consider" if total >= GW_CONSIDER else "low"
    timing = None
    if urgency != "low":
        timing = "by your first or second item" if any(a["early"] for a in sources) else "by your third item"
    return {"urgency": urgency, "timing": timing, "score": total,
            "sources": [{"champion": a["champion"], "score": a["score"], "reasons": a["reasons"]} for a in sources]}
