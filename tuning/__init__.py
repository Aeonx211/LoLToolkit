"""Tunable values for all three tools, with overrides saved in tuning.json at the repo root.

Only values that differ from the built-in defaults are written to the file. Every CLI and the web UI call apply()
on startup. Tool 1 results are cached under a hash of its tuning values, so changing them re-analyzes stored
games from the database with no extra API calls.
"""
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from build_sim import effects
from causal_analysis import archetypes, metrics
from live_advisor import build_predict, counters, healing, onetrick, threat

TUNING_FILE = Path(__file__).resolve().parent.parent / "tuning.json"


@dataclass
class Setting:
    key: str
    group: str
    label: str
    help: str
    get: Callable[[], Any]
    set: Callable[[Any], None]
    default: Any = None

    def __post_init__(self):
        self.default = self.get()

    def coerce(self, value):
        if isinstance(self.default, tuple):
            if isinstance(value, str):
                value = [v for v in value.replace(" ", "").split(",") if v]
            if len(value) != len(self.default):
                raise ValueError(f"{self.label}: expected {len(self.default)} numbers")
            return tuple(type(d)(float(v)) if isinstance(d, int) and float(v).is_integer() else float(v)
                         for d, v in zip(self.default, value))
        if isinstance(self.default, int) and not isinstance(self.default, bool):
            number = float(value)
            if not number.is_integer():
                raise ValueError(f"{self.label}: must be a whole number")
            return int(number)
        return float(value)


def _module(group, module, attr, label, help=""):
    return Setting(f"{module.__name__.split('.')[0]}.{attr}", group, label, help,
                   lambda: getattr(module, attr), lambda v: setattr(module, attr, v))


def _threshold(field, label, help=""):
    def set_value(v):
        archetypes.DEFAULT_THRESHOLDS = dataclasses.replace(archetypes.DEFAULT_THRESHOLDS, **{field: v})
    return Setting(f"causal_analysis.{field}", "Tool 1: archetype thresholds", label, help,
                   lambda: getattr(archetypes.DEFAULT_THRESHOLDS, field), set_value)


def _dict_entry(group, key, mapping, entry, label, help=""):
    def set_value(v):
        mapping[entry] = v
    return Setting(key, group, label, help, lambda: mapping[entry], set_value)


G2 = "Tool 2: live advisor"
G3 = "Tool 3: item and rune numbers"

SETTINGS = [
    _threshold("remake_s", "Remake cutoff (s)", "Games shorter than this are skipped."),
    _threshold("stomp_check_s", "Stomp check time (s)", "When the stomp lead is measured (900 = 15:00)."),
    _threshold("stomp_lead", "Stomp: min lead at check", "Winner's gold lead needed at the check time."),
    _threshold("stomp_max_counter_lead", "Stomp: loser's max lead", "Loser may never lead by more than this."),
    _threshold("stomp_floor", "Stomp: lead floor after check", "Winner's lead must stay above this afterwards."),
    _threshold("big_lead", "Comeback/Thrown: gold lead", "Gold lead that counts as 'winning' for Thrown/Comeback."),
    _threshold("thrown_kill_lead", "Thrown: kill lead", "Kill lead needed alongside the gold lead."),
    _threshold("snowball_min_lead", "Snowballed-on: loser's min lead", "Loser must have been ahead by this much."),
    _threshold("snowball_window_share", "Snowballed-on: window impact share",
               "Enemy player's share of team impact during the swing."),
    _threshold("snowball_ratio", "Snowballed-on: spike ratio", "Window share vs their share before the swing."),
    _threshold("snowball_min_kills", "Snowballed-on: min kills", "Kills by that player during the swing."),
    _threshold("carry_ratio", "Carried: impact vs role (floor)",
               "Impact must be at least this multiple of the role baseline to be eligible."),
    _threshold("carry_margin", "Carried: margin over next teammate",
               "How far (in impact_ratio) a player must lead the next-best teammate (or the whole team, if "
               "last) to qualify. Walking down from the top, players within this margin of each other co-carry "
               "together; the first gap this big or bigger stops the group."),
    _threshold("carry_min_impact", "Carried: min impact share", "Absolute floor on impact share (0-1)."),
    _threshold("even_band", "Even: gold band", "Gold diff must stay within this band..."),
    _threshold("even_until_frac", "Even: until fraction of game", "...until this fraction of the game (0-1)."),
    _threshold("even_min_duration_s", "Even: min game length (s)", ""),
    _threshold("fight_gap_s", "Fight grouping gap (s)", "Kills/objectives closer than this form one moment."),
    _threshold("rolling_window_s", "Rolling impact window (s)", ""),
    *[
        _dict_entry("Tool 1: role baselines (KP, damage, gold, tower, neutral, survival share)",
                    f"causal_analysis.ROLE_BASELINE.{role}", metrics.ROLE_BASELINE, role, role.title(),
                    "Typical kill participation, damage share, gold share, tower-damage share, neutral/epic-"
                    "monster-damage share, and survival share (1 - this role's share of the team's deaths, "
                    "so higher is fewer deaths than teammates). KP isn't exclusive (several players can be "
                    "credited per kill), so it runs ~45-65% rather than an even split.")
        for role in list(metrics.ROLE_BASELINE)
    ],
    _module("Tool 1: role baselines (KP, damage, gold, tower, neutral, survival share)", metrics, "TOWER_WEIGHT",
            "Impact: tower damage weight",
            "How much tower-damage share counts toward Impact, alongside KP/damage/gold (which always split "
            "the rest evenly)."),
    _module("Tool 1: role baselines (KP, damage, gold, tower, neutral, survival share)", metrics, "NEUTRAL_WEIGHT",
            "Impact: neutral/epic-monster damage weight",
            "How much dragon/herald/baron/grubs/atakhan damage share counts toward Impact. Kept higher than the "
            "tower weight: contesting/securing a neutral objective is a harder, more team-wide win than poking "
            "a tower."),
    _module("Tool 1: role baselines (KP, damage, gold, tower, neutral, survival share)", metrics, "DEATH_WEIGHT",
            "Impact: low-deaths bonus weight",
            "Bonus-only weight on surviving more than the role baseline (see role baselines' survival share). "
            "Never subtracts for dying more than baseline, only adds for dying less."),
    _module("Tool 1: role baselines (KP, damage, gold, tower, neutral, survival share)", metrics, "SHARE_CAP_RATIO",
            "Impact: per-component cap vs role baseline",
            "Ceiling on how far any single share (kp/damage/gold/tower/neutral) counts above its role baseline "
            "before being weighted, so one lumpy component can't swing the whole ratio alone."),
    _module(G2, threat, "MIN_WINS_TO_FLAG", "Carry flag: min recent wins"),
    _module(G2, threat, "CARRY_RATE_TO_FLAG", "Carry flag: carried-win rate", "0-1"),
    _module(G2, threat, "FULL_CONFIDENCE_WINS", "Carry score: wins for full confidence"),
    _module(G2, healing, "KIT_ABILITY_WEIGHT", "Grievous Wounds: points per healing ability",
            "Each of an enemy's abilities that heals (self or allies) adds this."),
    _module(G2, healing, "KIT_ABILITY_CAP", "Grievous Wounds: max points from abilities",
            "Cap for a champion who isn't a core healer."),
    _module(G2, healing, "CORE_HEALER_WEIGHT", "Grievous Wounds: core healer points",
            "Champions like Soraka or Aatrox, where healing is the point of the kit."),
    _module(G2, healing, "ITEM_WEIGHT", "Grievous Wounds: points per healing item",
            "Times how often they build it (100% if they already own it)."),
    _module(G2, healing, "ITEM_CAP", "Grievous Wounds: max points from items"),
    _module(G2, healing, "GW_CONSIDER", "Grievous Wounds: 'consider' at total points",
            "Enemy team's points add up; at or above this it's worth considering."),
    _module(G2, healing, "GW_HIGH", "Grievous Wounds: 'high priority' at total points"),
    _module(G2, onetrick, "POOL_GAMES", "One-trick: games checked", "Most recent games in the same queue."),
    _module(G2, onetrick, "ONE_TRICK_GAMES", "One-trick: games on one champion",
            "Out of the games checked. With fewer games on record, the same share is used."),
    _module(G2, onetrick, "MIN_POOL_GAMES", "One-trick: min games on record"),
    _module(G2, counters, "RESIST_SPLIT", "Resist advice: damage share", "Magic or physical share that means 'build that resist'."),
    _module(G2, counters, "EARLY_LANE_GOLD", "Tempo: 'strong early' lane gold @14"),
    _module(G2, counters, "SCALING_SHARE_GAIN", "Tempo: 'scales late' gold-share gain"),
    _module(G2, counters, "MAX_GAMES", "Games used per enemy profile"),
    _module(G2, build_predict, "FULL_CONFIDENCE_GAMES", "Build prediction: games for full confidence"),
    _module(G3, effects, "COMET_DEFAULT_RANGE_AMP", "Arcane Comet range amp", "0 = point blank, 1 = max range (+100%)."),
    _dict_entry(G3, "build_sim.BOTRK_CURRENT_HP.melee", effects.BOTRK_CURRENT_HP, "melee", "BotRK % current HP (melee)"),
    _dict_entry(G3, "build_sim.BOTRK_CURRENT_HP.ranged", effects.BOTRK_CURRENT_HP, "ranged", "BotRK % current HP (ranged)"),
    _module(G3, effects, "GRIEVOUS_WOUNDS", "Grievous Wounds healing cut"),
    _module(G3, effects, "LIANDRY_BURN", "Liandry's burn (% max HP over 3s)"),
    _module(G3, effects, "PLATED_STEELCAPS", "Plated Steelcaps attack reduction"),
    _module(G3, effects, "RANDUINS_OMEN", "Randuin's crit reduction"),
    _module(G3, effects, "SPIRIT_VISAGE", "Spirit Visage heal/shield amp"),
    _module(G3, effects, "NASHORS_TOOTH", "Nashor's Tooth", "flat, AP ratio"),
    _module(G3, effects, "WITS_END", "Wit's End on-hit"),
    _module(G3, effects, "KRAKEN_SLAYER", "Kraken Slayer", "damage at level 9, at level 19"),
    _module(G3, effects, "ELECTROCUTE", "Electrocute", "min, max (by level), bonus AD ratio, AP ratio, cooldown"),
    _module(G3, effects, "ARCANE_COMET", "Arcane Comet", "min, max, bonus AD ratio, AP ratio"),
    _module(G3, effects, "PRESS_THE_ATTACK", "Press the Attack", "min, max, damage amp"),
    _module(G3, effects, "CONQUEROR", "Conqueror",
            "AF/stack min, max, max stacks, duration, heal melee, heal ranged"),
    _module(G3, effects, "DARK_HARVEST", "Dark Harvest",
            "base, per soul, bonus AD ratio, AP ratio, cooldown, HP threshold"),
]
BY_KEY = {s.key: s for s in SETTINGS}


def _encode(value):
    return list(value) if isinstance(value, tuple) else value


def describe():
    groups = {}
    for s in SETTINGS:
        groups.setdefault(s.group, []).append({
            "key": s.key, "label": s.label, "help": s.help,
            "value": _encode(s.get()), "default": _encode(s.default),
        })
    return [{"group": g, "settings": items} for g, items in groups.items()]


def load_overrides():
    if not TUNING_FILE.exists():
        return {}
    return json.loads(TUNING_FILE.read_text(encoding="utf-8"))


def apply():
    for key, value in load_overrides().items():
        if key in BY_KEY:
            BY_KEY[key].set(BY_KEY[key].coerce(value))


def update(values: dict):
    """Validate and apply new values, then save any that differ from the defaults."""
    coerced = {}
    for key, value in values.items():
        if key not in BY_KEY:
            raise ValueError(f"Unknown setting {key!r}")
        coerced[key] = BY_KEY[key].coerce(value)
    for key, value in coerced.items():
        BY_KEY[key].set(value)
    _save()


def reset(keys=None):
    for s in SETTINGS if keys is None else [BY_KEY[k] for k in keys]:
        s.set(s.default)
    _save()


def _save():
    overrides = {s.key: _encode(s.get()) for s in SETTINGS if s.get() != s.default}
    if overrides:
        TUNING_FILE.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")
    elif TUNING_FILE.exists():
        TUNING_FILE.unlink()
