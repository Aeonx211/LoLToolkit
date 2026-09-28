import json
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://ddragon.leagueoflegends.com"
USER_AGENT = "LoLInsightToolkit/0.1"


def _fetch(url):
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as resp:
        return json.load(resp)


class DataDragon:
    """Static champion/item data, cached on disk per patch version."""

    def __init__(self, cache_dir, locale="en_US"):
        self._dir = Path(cache_dir) / "ddragon"
        self._locale = locale
        self._versions = None

    def versions(self):
        if self._versions is None:
            self._versions = _fetch(f"{BASE}/api/versions.json")
        return self._versions

    def latest_version(self):
        return self.versions()[0]

    def version_for_game(self, game_version):
        """Map a match's gameVersion (e.g. '15.19.712.1234') to a Data Dragon version."""
        prefix = ".".join(game_version.split(".")[:2]) + "."
        return next((v for v in self.versions() if v.startswith(prefix)), self.latest_version())

    def _cached(self, version, name):
        version = version or self.latest_version()
        path = self._dir / version / self._locale / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = _fetch(f"{BASE}/cdn/{version}/data/{self._locale}/{name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def derived(self, name, build):
        """A table computed from Data Dragon, cached beside the raw files so it's rebuilt once per patch."""
        version = self.latest_version()
        path = self._dir / version / self._locale / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = build(version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def champions(self, version=None):
        return self._cached(version, "champion.json")["data"]

    def champion(self, champion_id, version=None):
        return self._cached(version, f"champion/{champion_id}.json")["data"][champion_id]

    def items(self, version=None):
        return self._cached(version, "item.json")["data"]
