import argparse
import json
import sys
from datetime import datetime

from data_layer import DataLayer

from .metrics import describe_moment, fmt_gold, mmss
from .parse import TEAM_NAMES
from .service import analyze_match_id, analyze_player

QUEUES = {400: "Draft", 420: "Ranked Solo", 430: "Blind", 440: "Ranked Flex", 450: "ARAM", 490: "Quickplay",
          700: "Clash", 900: "URF", 1700: "Arena", 1900: "URF"}


def _tag_labels(result):
    labels = []
    for tag in result["tags"]:
        d = tag["detail"]
        if "champion" in d:
            labels.append(f"{tag['archetype']}: {d['champion']}")
        elif tag["team"]:
            labels.append(f"{tag['archetype']} ({TEAM_NAMES[tag['team']]})")
        else:
            labels.append(tag["archetype"])
    return ", ".join(labels) or "no archetype"


def print_player_line(result, puuid):
    me = next(p for p in result["players"] if p["puuid"] == puuid)
    when = datetime.fromtimestamp(result["game_start"] / 1000).strftime("%Y-%m-%d")
    queue = QUEUES.get(result["queue_id"], f"queue {result['queue_id']}")
    k, d, a = me["kda"]
    print(f"{result['match_id']}  {when}  {queue:<11}  {mmss(result['duration_s'])}  "
          f"{'WIN ' if me['win'] else 'LOSS'}  {me['champion']} {me['position'].lower()} "
          f"({TEAM_NAMES[me['team_id']]}) {k}/{d}/{a}  impact {me['impact_ratio']:.2f}x")
    print(f"  [{_tag_labels(result)}]")
    print(f"  {result['verdict']}\n")


def print_match_detail(result):
    if "skipped" in result:
        print(f"{result['match_id']} skipped: {result['skipped']}")
        return
    print(f"{result['match_id']}  {mmss(result['duration_s'])}  {TEAM_NAMES[result['winner']]} won")
    print(f"Tags: {_tag_labels(result)}")
    print(f"\n{result['verdict']}\n")
    leads = result["leads"]
    for team, peak in leads["gold_peaks"].items():
        print(f"  {TEAM_NAMES[int(team)]} max gold lead: {fmt_gold(peak['lead'])} at {mmss(peak['at'])}")
    if leads["gold_flips"]:
        print(f"  Lead changed hands at: {', '.join(mmss(t) for t in leads['gold_flips'])}")
    print("\nKey moments:")
    for m in result["key_moments"]:
        print(f"  {describe_moment(m)}")
    print("\nPlayers:")
    for p in result["players"]:
        s = p["shares"]
        flag = "  <- carried" if p["carried"] else ""
        print(f"  {TEAM_NAMES[p['team_id']]:<4} {p['champion']:<13} {p['position'].lower():<8} "
              f"kills {s['kills']:.0%}  dmg {s['damage']:.0%}  gold {s['gold']:.0%}  "
              f"impact {p['impact_ratio']:.2f}x  {p['riot_id']}{flag}")


def main(argv=None):
    import tuning
    tuning.apply()
    parser = argparse.ArgumentParser(prog="causal_analysis", description="Explain why League games were won or lost.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_player = sub.add_parser("player", help="analyze a player's recent matches")
    p_player.add_argument("riot_id", help="e.g. Aeoen#NA1")
    p_player.add_argument("-n", "--count", type=int, default=10)
    p_player.add_argument("-q", "--queue", type=int, help="queue id filter, e.g. 420 for ranked solo")
    p_player.add_argument("--json", action="store_true")
    p_match = sub.add_parser("match", help="analyze one match in detail")
    p_match.add_argument("match_id", help="e.g. NA1_5123456789")
    p_match.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    layer = DataLayer.from_env()
    if args.command == "match":
        result = analyze_match_id(layer, args.match_id)
        if result is None:
            sys.exit(f"Match {args.match_id} not found")
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_match_detail(result)
        return

    puuid = layer.resolve_riot_id(args.riot_id)
    if args.json:
        _, results = analyze_player(layer, args.riot_id, args.count, args.queue)
        print(json.dumps(results, indent=2))
        return
    analyze_player(layer, args.riot_id, args.count, args.queue,
                   on_result=lambda r: print_player_line(r, puuid))
    rollup = layer.store.get_rollup(puuid)
    if rollup and rollup["wins"]:
        print(f"All stored games: {rollup['wins']}/{rollup['games']} wins, carried in "
              f"{rollup['carried_wins']}/{rollup['wins']} wins ({rollup['carry_rate_in_wins']:.0%})")


if __name__ == "__main__":
    main()
