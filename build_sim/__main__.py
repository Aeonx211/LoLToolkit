import argparse
import json
import sys
from pathlib import Path

from data_layer import load_settings

from .data import GameData
from .scenario import breakpoints, compare, run_scenario


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _side_line(side):
    t = side["by_type"]
    extra = []
    if side["healing"]:
        extra.append(f"healed {side['healing']}")
    if side["shielding"]:
        extra.append(f"shielded {side['shielding']}")
    death = f", died at {side['died_at']}s" if side["died_at"] is not None else ""
    return (f"{side['name']:<18} dealt {side['damage_dealt']:>5} "
            f"(phys {t['physical']}, magic {t['magic']}, true {t['true']})"
            + (f", {', '.join(extra)}" if extra else "")
            + f"  HP {side['hp_end']}/{side['hp_start']}{death}")


def print_result(r, title=None, log=False):
    if title:
        print(f"== {title}")
    s = r["attacker"]["stats"]
    print(f"{r['attacker']['name']} lvl {s['level']}: {s['hp']} HP, {s['ad']} AD, {s['ap']} AP, "
          f"{s['attack_speed']} AS, ranks {' '.join(f'{k}{v}' for k, v in s['ranks'].items())}")
    print(_side_line(r["attacker"]))
    print(_side_line(r["target"]))
    print(f"Trade: {r['net_trade']:+d} HP in your favor over {r['duration']}s")
    if log:
        for e in r["log"]:
            amount = f"{e['amount']:>7.1f} {e['type']}" if e["type"] else ""
            print(f"  {e['t']:>5.2f}s  {e['source']:<16} {e['what']:<20} {amount}")
    for a in r["assumptions"]:
        print(f"  assumes {a}")
    if r["unmodeled_passives"]:
        print(f"  stats only (passive not modeled): {', '.join(r['unmodeled_passives'])}")
    print()


def main(argv=None):
    import tuning
    tuning.apply()
    parser = argparse.ArgumentParser(prog="build_sim", description="Simulate a combo/trade for a build.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="simulate a scenario file")
    p_run.add_argument("scenario")
    p_run.add_argument("--log", action="store_true", help="print every damage event")
    p_run.add_argument("--json", action="store_true")
    p_cmp = sub.add_parser("compare", help="A/B the scenario's attacker against another build")
    p_cmp.add_argument("scenario")
    p_cmp.add_argument("build_b", help="JSON with the fields to override (items, runes, level, ...)")
    p_bp = sub.add_parser("breakpoints", help="swap each item/keystone and rank the changes")
    p_bp.add_argument("scenario")
    p_bp.add_argument("--candidates", help="comma-separated item names (default: all legendaries of your type)")
    p_bp.add_argument("--top", type=int, default=15)
    args = parser.parse_args(argv)

    data = GameData(load_settings().cache_dir)
    scenario = _load(args.scenario)
    try:
        if args.command == "run":
            r = run_scenario(data, scenario)
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                print_result(r, log=args.log)
        elif args.command == "compare":
            a, b = compare(data, scenario, _load(args.build_b))
            print_result(a, "A (scenario)")
            print_result(b, f"B ({args.build_b})")
            diff = b["attacker"]["damage_dealt"] - a["attacker"]["damage_dealt"]
            print(f"B vs A: {diff:+d} damage, {b['net_trade'] - a['net_trade']:+d} trade")
        else:
            candidates = [c.strip() for c in args.candidates.split(",")] if args.candidates else None
            base, rows = breakpoints(data, scenario, candidates)
            print_result(base, "Baseline")
            def line(r):
                kill = f"  (kills at {r['kills_at']}s)" if r["kills_at"] is not None else ""
                return f"  {r['damage']:+6d} dmg  {r['net_trade']:+6d} trade  {r['gold']:+5d}g  {r['change']}{kill}"

            by = "fastest kill" if base["target"]["died_at"] is not None else "damage"
            print(f"Top {args.top} swaps by {by} (boots are left alone):")
            for r in rows[:args.top]:
                print(line(r))
            print("\nWorst 5:")
            for r in rows[-5:]:
                print(line(r))
    except (KeyError, ValueError) as e:
        sys.exit(f"error: {e.args[0] if e.args else e}")


if __name__ == "__main__":
    main()
