"""Item passives and runes the simulator models.

Item numbers come from Meraki's item data and rune numbers from CommunityDragon's perks.json. Both were
pulled in September 2026 (Data Dragon 16.19.1).
TODO: re-verify these each patch; unlike item stats, which are parsed live from Data Dragon, these are hand-entered.
"""
from dataclasses import dataclass, field

# Spellblade items don't stack; the strongest one owned applies. (damage type, base AD ratio, AP ratio)
SPELLBLADE = {
    "trinityforce": ("physical", 2.00, 0.00),
    "lichbane": ("magic", 0.75, 0.40),
    "sheen": ("physical", 1.00, 0.00),
}
SPELLBLADE_PRIORITY = ["trinityforce", "lichbane", "sheen"]
SPELLBLADE_CD = 1.5
SPELLBLADE_WINDOW = 10.0

NASHORS_TOOTH = (15, 0.15)          # flat, AP ratio; magic on-hit
WITS_END = 45                       # magic on-hit
KRAKEN_SLAYER = (150, 200)          # every 3rd attack, levels 9-19 scale; ranged deal 80%
BOTRK_CURRENT_HP = {"melee": 0.08, "ranged": 0.05}  # TODO: not in Meraki's text; value unverified
LIANDRY_BURN = 0.06                 # of target max HP over 3s, 1% per 0.5s tick
LIANDRY_SUFFERING = (0.02, 3)       # +2% damage per second in combat, up to 3 stacks
BLACK_CLEAVER = (0.06, 5, 6.0)      # armor reduction per stack, max stacks, duration
PLATED_STEELCAPS = 0.10             # less basic-attack damage taken
RANDUINS_OMEN = 0.30                # less crit damage taken
SPIRIT_VISAGE = 0.25                # more healing and shielding received
THORNMAIL = (20, 0.10)              # flat + bonus armor ratio, magic, when struck by an attack
GRIEVOUS_WOUNDS = 0.40              # TODO: verify current healing reduction
GW_DURATION = 3.0
GW_ON_MAGIC = {"morellonomicon", "oblivionorb"}
GW_ON_PHYSICAL = {"mortalreminder", "executionerscalling", "chempunkchainsword"}
GW_WHEN_ATTACKED = {"thornmail", "bramblevest"}

MODELED_ITEMS = (set(SPELLBLADE) | {"nashorstooth", "witsend", "krakenslayer", "bladeoftheruinedking",
                                    "liandrystorment", "blackcleaver", "platedsteelcaps", "randuinsomen",
                                    "spiritvisage", "rabadonsdeathcap", "shadowflame"}
                 | GW_ON_MAGIC | GW_ON_PHYSICAL | GW_WHEN_ATTACKED)

ELECTROCUTE = (70, 240, 0.10, 0.05, 20.0)     # lo, hi (by level), bonus AD ratio, AP ratio, cooldown
ARCANE_COMET = (15, 100, 0.10, 0.05)          # lo, hi, bonus AD ratio, AP ratio; cooldown 20 -> 8 by level
COMET_DEFAULT_RANGE_AMP = 0.5                 # TODO: comet scales up to +100% at 750 range; 0.5 is a guess
PRESS_THE_ATTACK = (40, 160, 0.08)            # lo, hi, damage amp after proc
CONQUEROR = (1.8, 4.0, 12, 5.0, 0.08, 0.05)   # AF per stack lo/hi, max stacks, duration, heal melee/ranged
DARK_HARVEST = (30, 11, 0.10, 0.05, 35.0, 0.5)  # base, per soul, bAD, AP, cooldown, HP threshold
KEYSTONES = {"Electrocute", "Arcane Comet", "Press the Attack", "Conqueror", "Dark Harvest", None}

COUP_DE_GRACE = (0.08, 0.40)
CUT_DOWN = (0.08, 0.60)
LAST_STAND = (0.05, 0.11, 0.60, 0.30)
ABSOLUTE_FOCUS = (3, 30, 0.70)                # adaptive force by level, while above 70% HP
MINOR_RUNES = {"Coup de Grace", "Cut Down", "Last Stand", "Absolute Focus"}

SHARDS = {
    "adaptive": {"adaptive_force": 9},
    "attack_speed": {"attack_speed": 0.10},
    "haste": {"haste": 8},
    "health": {"hp": 65},
    "scaling_health": {"hp_by_level": (10, 180)},
}


@dataclass
class Runes:
    keystone: str | None = None
    minor: list[str] = field(default_factory=list)
    shards: list[str] = field(default_factory=list)
    comet_range_amp: float | None = None  # None -> COMET_DEFAULT_RANGE_AMP (read at sim time so tuning applies)
    dark_harvest_souls: int = 0

    def validate(self):
        if self.keystone not in KEYSTONES:
            raise ValueError(f"Keystone {self.keystone!r} isn't modeled; choose from "
                             f"{sorted(k for k in KEYSTONES if k)}")
        for m in self.minor:
            if m not in MINOR_RUNES:
                raise ValueError(f"Rune {m!r} isn't modeled; choose from {sorted(MINOR_RUNES)}")
        for s in self.shards:
            if s not in SHARDS:
                raise ValueError(f"Shard {s!r} unknown; choose from {sorted(SHARDS)}")
