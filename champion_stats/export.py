"""Write the Champion Stats tab as one self-contained HTML file, with the game rows built in, so it opens with no
server (e.g. on a phone):

    python -m champion_stats.export "Name#TAG" Champion [--queue solo|flex|both] [-o champion_stats.html]
                                    [--save-data snapshots/champion_stats/NAME.json]
    python -m champion_stats.export --from-data snapshots/champion_stats/NAME.json [-o champion_stats.html]

It refreshes the backfill first (only new games are fetched), so it needs RIOT_API_KEY like the web UI. --save-data
also writes the page's data to a JSON snapshot that can be committed; --from-data rebuilds the page from such a
snapshot with no Riot key or network (e.g. in a cloud session), showing the games as of that snapshot."""

import argparse
import html
import json
import sys
import time
from pathlib import Path

from data_layer import DataDragon, DataLayer, load_settings

from .service import QUEUES, load_rows

STATIC = Path(__file__).resolve().parent.parent / "webui" / "static"
# app.js's helper section (h, fill, pct, champName, saved, cache, ...) ends where its tab code starts.
HELPERS_END = "// ---------- tabs"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Champion Stats</title>
<link rel="icon" href="data:,">
<style>
{css}
.cs-export-head {{ margin: 0 0 4px; font-size: 20px; }}
</style>
</head>
<body>
<main>
  <h1 class="cs-export-head">{title}</h1>
  <div class="muted">{subtitle}</div>
  <form id="cs-form" class="toolbar" onsubmit="return false">
    <label>Patches <select name="patch_from"></select> to <select name="patch_to"></select></label>
    <button type="button" name="all_patches" title="Clear the patch range">All patches</button>
    <label>Min games <input name="min_games" type="number" min="1" max="50" value="5" class="narrow"></label>
  </form>
  <div id="cs-out"></div>
</main>
<script>
{helpers}
</script>
<script>
{tab}
</script>
<script>
const CS_EXPORT = {data};
META = {{ champions: CS_EXPORT.champions || {{}} }};
csWireSlice($("#cs-form"));
csShow(CS_EXPORT);
</script>
</body>
</html>
"""

QUEUE_NAMES = {"solo": "Ranked Solo", "flex": "Ranked Flex", "both": "Ranked Solo + Flex"}


def _script(text):
    return text.replace("</script", "<\\/script")


def build_html(data, champions=None, exported_at=None):
    """The page for one load_rows() result. `champions` maps Riot's internal names to display names."""
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    if HELPERS_END not in app_js:
        raise RuntimeError(f"app.js no longer has the {HELPERS_END!r} marker the export relies on")
    exported_at = exported_at or time.time()
    payload = {k: v for k, v in data.items() if k != "puuid"}
    payload["champions"] = champions or {}
    payload["savedAt"] = int(exported_at * 1000)
    champion = (champions or {}).get(data["champion"], data["champion"])
    when = time.strftime("%b %d, %Y", time.localtime(exported_at))
    return PAGE.format(
        css=(STATIC / "style.css").read_text(encoding="utf-8"),
        title=html.escape(f"{champion} · {data['riot_id']}"),
        subtitle=html.escape(f"{len(data['rows'])} {QUEUE_NAMES.get(data['queue'], data['queue'])} games · exported {when}"),
        helpers=_script(app_js[:app_js.index(HELPERS_END)]),
        tab=_script((STATIC / "champion_stats.js").read_text(encoding="utf-8")),
        data=_script(json.dumps(payload, separators=(",", ":"))),
    )


def save_snapshot(path, data, champions=None, exported_at=None):
    """Write what build_html needs as JSON, without the puuid, so the page can be rebuilt offline later."""
    snapshot = {"data": {k: v for k, v in data.items() if k != "puuid"}, "champions": champions or {},
                "exported_at": exported_at if exported_at is not None else time.time()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_snapshot(path):
    """(data, champions, exported_at) as save_snapshot wrote them. JSON turns int keys (item and rune ids) into
    strings, which is how the page reads them anyway."""
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    return snapshot["data"], snapshot.get("champions", {}), snapshot.get("exported_at")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="champion_stats.export", description=__doc__.split("\n\n")[0])
    parser.add_argument("riot_id", nargs="?")
    parser.add_argument("champion", nargs="?")
    parser.add_argument("--queue", choices=list(QUEUES), default="solo")
    parser.add_argument("-o", "--output", default="champion_stats.html")
    parser.add_argument("--save-data", metavar="JSON", help="also write the page's data to this snapshot file")
    parser.add_argument("--from-data", metavar="JSON", help="build from a snapshot instead of the Riot API")
    args = parser.parse_args(argv)
    if args.from_data:
        data, champions, exported_at = load_snapshot(args.from_data)
    else:
        if not (args.riot_id and args.champion):
            parser.error("give a Riot ID and champion, or --from-data")
        dd = DataDragon(load_settings().cache_dir)
        data = load_rows(DataLayer.from_env(), args.riot_id, args.champion, args.queue,
                         progress=lambda m: print(m, file=sys.stderr), dd=dd)
        try:
            champions = {c["id"]: c["name"] for c in dd.champions().values()}
        except OSError:
            champions = {}
        exported_at = time.time()
        if args.save_data:
            save_snapshot(args.save_data, data, champions, exported_at)
            print(f"Saved {args.save_data}", file=sys.stderr)
    Path(args.output).write_text(build_html(data, champions, exported_at), encoding="utf-8")
    print(f"Wrote {args.output} ({len(data['rows'])} games)", file=sys.stderr)


if __name__ == "__main__":
    main()
