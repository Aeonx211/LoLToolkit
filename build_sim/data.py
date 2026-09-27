import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from data_layer import DataDragon

MERAKI_CHAMPION = "https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions/{}.json"
USER_AGENT = "LoLInsightToolkit/0.1"

# Item stat lines as they appear in Data Dragon's description <stats> block.
STAT_LABELS = {
    "Attack Damage": "ad",
    "Ability Power": "ap",
    "Health": "hp",
    "Armor": "armor",
    "Magic Resist": "mr",
    "Attack Speed": "attack_speed",
    "Critical Strike Chance": "crit",
    "Critical Strike Damage": "crit_damage",
    "Lethality": "lethality",
    "Armor Penetration": "armor_pen",
    "Magic Penetration": ("magic_pen_flat", "magic_pen_pct"),
    "Ability Haste": "haste",
    "Life Steal": "lifesteal",
    "Omnivamp": "omnivamp",
}
_STATS_BLOCK = re.compile(r"<stats>(.*?)</stats>", re.S)
_STAT_LINE = re.compile(r"<attention>\s*([\d.]+)(%?)\s*</attention>\s*([^<]+?)\s*(?=<br>|$)")
_AP_AMP = re.compile(r"Ability Power by (\d+)%")
_EXECUTE_AMP = re.compile(r"below (\d+)% Health, dealing (\d+)% increased damage")


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_item_stats(description):
    block = _STATS_BLOCK.search(description or "")
    if not block:
        return {}
    stats = {}
    for value, pct, label in _STAT_LINE.findall(block.group(1)):
        key = STAT_LABELS.get(label.strip())
        if key is None:
            continue
        if isinstance(key, tuple):
            key = key[1] if pct else key[0]
        amount = float(value) / 100 if pct else float(value)
        stats[key] = stats.get(key, 0) + amount
    return stats


@dataclass
class Item:
    id: str
    name: str
    key: str
    cost: int
    stats: dict
    description: str
    ap_amp: float = 0.0
    execute_threshold: float = 0.0
    execute_amp: float = 0.0

    @property
    def has_passive(self):
        return "<passive>" in self.description or "<active>" in self.description


class GameData:
    """Champion base stats + items from Data Dragon, ability numbers from Meraki; all cached on disk."""

    def __init__(self, cache_dir, version=None):
        self._cache = Path(cache_dir)
        self.dd = DataDragon(cache_dir)
        self.version = version or self.dd.latest_version()
        self._items = None

    def champion_key(self, name):
        champions = self.dd.champions(self.version)
        wanted = norm(name)
        for key, c in champions.items():
            if norm(key) == wanted or norm(c["name"]) == wanted:
                return key
        close = difflib.get_close_matches(name, [c["name"] for c in champions.values()], n=3)
        raise KeyError(f"Unknown champion {name!r}" + (f"; did you mean {', '.join(close)}?" if close else ""))

    def champion_stats(self, key):
        return self.dd.champion(key, self.version)["stats"]

    def meraki(self, key):
        path = self._cache / "meraki" / f"{key}.json"
        if not path.exists():
            with urlopen(Request(MERAKI_CHAMPION.format(key), headers={"User-Agent": USER_AGENT}), timeout=30) as r:
                data = json.load(r)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        return json.loads(path.read_text(encoding="utf-8"))

    def items(self):
        if self._items is None:
            by_key = {}
            for item_id, it in sorted(self.dd.items(self.version).items(), key=lambda kv: int(kv[0])):
                if not it.get("maps", {}).get("11") or not it["gold"].get("purchasable"):
                    continue
                key = norm(it["name"])
                if key in by_key:
                    continue
                desc = it.get("description", "")
                item = Item(item_id, it["name"], key, it["gold"]["total"], parse_item_stats(desc), desc)
                if m := _AP_AMP.search(desc):
                    item.ap_amp = int(m.group(1)) / 100
                if m := _EXECUTE_AMP.search(desc):
                    item.execute_threshold, item.execute_amp = int(m.group(1)) / 100, int(m.group(2)) / 100
                by_key[key] = item
            self._items = by_key
        return self._items

    def item(self, name):
        items = self.items()
        key = norm(name)
        if key in items:
            return items[key]
        close = difflib.get_close_matches(name, [i.name for i in items.values()], n=3)
        raise KeyError(f"Unknown item {name!r}" + (f"; did you mean {', '.join(close)}?" if close else ""))
