from dataclasses import dataclass

AS_CAP = 2.5


def growth(level):
    """Riot's per-level stat growth multiplier."""
    return (level - 1) * (0.7025 + 0.0175 * (level - 1))


def by_level(lo, hi, level):
    return lo + (hi - lo) * (level - 1) / 17


@dataclass
class Stats:
    level: int
    base_hp: float
    max_hp: float
    armor: float
    bonus_armor: float
    mr: float
    base_ad: float
    bonus_ad: float
    ap_raw: float
    ap_amp: float
    attack_speed: float
    bonus_attack_speed: float
    crit: float = 0.0
    crit_damage: float = 1.75
    lethality: float = 0.0
    armor_pen: float = 0.0
    magic_pen_flat: float = 0.0
    magic_pen_pct: float = 0.0
    haste: float = 0.0
    lifesteal: float = 0.0
    omnivamp: float = 0.0

    @property
    def ad(self):
        return self.base_ad + self.bonus_ad

    @property
    def ap(self):
        return self.ap_raw * (1 + self.ap_amp)

    @property
    def bonus_hp(self):
        return self.max_hp - self.base_hp


def champion_stats(base, level, items=(), extra=None, adaptive_force=0.0, adaptive="magic", as_ratio=None):
    """Combine Data Dragon base stats, per-level growth, item stats and flat rune/shard bonuses."""
    extra = extra or {}
    g = growth(level)
    total = {}
    for item in items:
        for k, v in item.stats.items():
            total[k] = total.get(k, 0) + v
    for k, v in extra.items():
        total[k] = total.get(k, 0) + v

    base_hp = base["hp"] + base["hpperlevel"] * g
    base_armor = base["armor"] + base["armorperlevel"] * g
    base_ad = base["attackdamage"] + base["attackdamageperlevel"] * g
    bonus_ad = total.get("ad", 0) + (0.6 * adaptive_force if adaptive == "physical" else 0)
    ap_raw = total.get("ap", 0) + (adaptive_force if adaptive == "magic" else 0)
    bonus_as = base["attackspeedperlevel"] / 100 * g + total.get("attack_speed", 0)
    ratio = as_ratio or base["attackspeed"]
    return Stats(
        level=level,
        base_hp=base_hp,
        max_hp=base_hp + total.get("hp", 0),
        armor=base_armor + total.get("armor", 0),
        bonus_armor=total.get("armor", 0),
        mr=base["spellblock"] + base["spellblockperlevel"] * g + total.get("mr", 0),
        base_ad=base_ad,
        bonus_ad=bonus_ad,
        ap_raw=ap_raw,
        ap_amp=sum(getattr(i, "ap_amp", 0) for i in items),
        attack_speed=min(AS_CAP, base["attackspeed"] + ratio * bonus_as),
        bonus_attack_speed=bonus_as,
        crit=min(1.0, total.get("crit", 0)),
        crit_damage=1.75 + total.get("crit_damage", 0),
        lethality=total.get("lethality", 0),
        armor_pen=total.get("armor_pen", 0),
        magic_pen_flat=total.get("magic_pen_flat", 0),
        magic_pen_pct=total.get("magic_pen_pct", 0),
        haste=total.get("haste", 0),
        lifesteal=total.get("lifesteal", 0),
        omnivamp=total.get("omnivamp", 0),
    )


def dummy_stats(hp, armor, mr):
    return Stats(level=1, base_hp=hp, max_hp=hp, armor=armor, bonus_armor=0, mr=mr, base_ad=0, bonus_ad=0,
                 ap_raw=0, ap_amp=0, attack_speed=0.0, bonus_attack_speed=0)
