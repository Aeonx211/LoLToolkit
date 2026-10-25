"""Write the Champion Stats tab as one self-contained HTML file, with the game rows built in, so it opens with no
server (e.g. on a phone):

    python -m champion_stats.export "Name#TAG" Champion [--queue solo|flex|both] [-o champion_stats.html]

It refreshes the backfill first (only new games are fetched), so it needs RIOT_API_KEY like the web UI."""

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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="champion_stats.export", description=__doc__.split("\n\n")[0])
    parser.add_argument("riot_id")
    parser.add_argument("champion")
    parser.add_argument("--queue", choices=list(QUEUES), default="solo")
    parser.add_argument("-o", "--output", default="champion_stats.html")
    args = parser.parse_args(argv)
    settings = load_settings()
    dd = DataDragon(settings.cache_dir)
    data = load_rows(DataLayer.from_env(), args.riot_id, args.champion, args.queue,
                     progress=lambda m: print(m, file=sys.stderr), dd=dd)
    try:
        champions = {c["id"]: c["name"] for c in dd.champions().values()}
    except OSError:
        champions = {}
    Path(args.output).write_text(build_html(data, champions), encoding="utf-8")
    print(f"Wrote {args.output} ({len(data['rows'])} games)", file=sys.stderr)


if __name__ == "__main__":
    main()
