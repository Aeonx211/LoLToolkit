import argparse
import json
import sys

from causal_analysis.metrics import mmss
from data_layer import DataDragon, DataLayer, load_settings

from .advisor import build_report, resolve_roster


def _pct(x):
    return f"{round(x * 100)}%"


def print_report(report, names=None):
    names = names or {}
    name = lambda champion: names.get(champion, champion)
    print(f"Live advisor ({report['source']})\n")
    focus = report["focus_target"]
    if focus:
        print(f"FOCUS: {name(focus['champion'])} ({focus['riot_id']}): tagged as the carry in "
              f"{focus['carried_wins']}/{focus['wins']} recent wins ({_pct(focus['carry_rate'])})\n")
    else:
        print("No enemy has a consistent carry record in their recent wins.\n")

    print("Carry threats (enemy):")
    for t in report["carry_threats"]:
        impact = f"{t['avg_impact']:.2f}x" if t["avg_impact"] is not None else "n/a"
        mark = "  <- flagged" if t["flagged"] else ""
        print(f"  {name(t['champion']):<13} carried {t['carried_wins']}/{t['wins']} wins, avg impact {impact} over "
              f"{t['games']} games{mark}   {t['riot_id']}")
    for a in report.get("ally_carries", []):
        if a is report["ally_carries"][0]:
            print("\nYour team's likely carries:")
        print(f"  {name(a['champion']):<13} carried {a['carried_wins']}/{a['wins']} wins   {a['riot_id']}")

    c = report["counters"]
    s = c["damage_split"]
    print(f"\nEnemy damage: {_pct(s['physical'])} physical / {_pct(s['magic'])} magic / {_pct(s['true'])} true")
    print(f"  {c['resist_advice']}")
    gw = c["grievous_wounds"]
    if gw["sources"]:
        timing = f", {gw['timing']}" if gw["timing"] else ""
        print(f"  Grievous Wounds: {gw['urgency']} priority{timing}")
        for src in gw["sources"]:
            print(f"    {name(src['champion'])}: {'; '.join(src['reasons']) or 'some healing'}")
    else:
        print("  Grievous Wounds: low priority (no enemy healing found)")

    print("\nEnemies:")
    for e in report["enemies"]:
        p = e["profile"]
        tempo = ", ".join(p["tempo"]) or "no clear tempo"
        lane = f", lane gold @14 {p['lane_gold_diff_14']:+d}" if p.get("lane_gold_diff_14") is not None else ""
        print(f"  {name(e['champion'])} ({e['riot_id']}): {tempo}{lane}  [{p['games']} {p['source']}]")
        pool = e["pool"]
        if pool and pool["one_trick"]:
            on_it = "" if pool["on_it"] else " (not playing it now)"
            print(f"    ONE-TRICK: {name(pool['champion'])}, {pool['games']} of their last {pool['total']} games{on_it}")
        b = e["build_prediction"]
        if b:
            build = " > ".join(f"{i['item']} {_pct(i['rate'])}" for i in b["modal_build"])
            spikes = ", ".join(mmss(t) for t in b["item_spikes_s"])
            print(f"    Build ({b['games']} games, confidence {_pct(b['confidence'])}): {build}")
            print(f"    First item {b['first_item']['item']} ({_pct(b['first_item']['rate'])})"
                  + (f"; item spikes at {spikes}" if spikes else ""))
        if e["live"]:
            print(f"    Now: level {e['live']['level']}, items: {', '.join(e['live']['items']) or 'none'}")


def main(argv=None):
    import tuning
    tuning.apply()
    parser = argparse.ArgumentParser(prog="live_advisor", description="Carry targets and counter-itemization "
                                                                      "for the game you're in.")
    parser.add_argument("riot_id", help="your Riot ID, e.g. Aeoen#NA1")
    parser.add_argument("--depth", type=int, default=8, help="recent games to analyze per player (default 8)")
    parser.add_argument("--allies", action="store_true", help="also analyze your own team")
    parser.add_argument("--replay", metavar="MATCH_ID", help="run against a finished match instead of a live game")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    layer = DataLayer.from_env()
    dd = DataDragon(load_settings().cache_dir)
    try:
        roster = resolve_roster(layer, dd, args.riot_id, args.replay)
    except LookupError as e:
        sys.exit(str(e))

    progress = None if args.json else lambda msg: print(msg, file=sys.stderr)
    report = build_report(layer, dd, roster, args.depth, args.allies, progress)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, {c["id"]: c["name"] for c in dd.champions().values()})


if __name__ == "__main__":
    main()
