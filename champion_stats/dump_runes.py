"""Print the tracked player's per-game rune values as JSON, for checking rune_labels.py against real games:
python -m champion_stats.dump_runes "Name#TAG" Champion > rune_values.json"""

import json
import sys

from data_layer import DataDragon, DataLayer, load_settings

from .rune_labels import RUNE_VALUE_LABELS
from .service import load_rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        sys.exit(__doc__)
    data = load_rows(DataLayer.from_env(), argv[0], argv[1], "solo", progress=lambda m: print(m, file=sys.stderr),
                     dd=DataDragon(load_settings().cache_dir))
    games = [{"match_id": r["match_id"], "patch": r["patch"], "win": r["win"], "duration_s": r["duration_s"],
              "rune_values": r["rune_values"]} for r in data["rows"]]
    json.dump({"labels": {str(k): v for k, v in RUNE_VALUE_LABELS.items()}, "games": games}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
