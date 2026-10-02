"""Probe whether the local League client can download replays (.rofl) of another player's games.

Run on the machine where the League client is open and logged in:
    python -m replay_probe "Reus#FIRST" --platform euw1 -n 5

It lists the player's recent matches via Match-V5, then asks the client's local LCU API to download each
replay and reports what the client said. The LCU is only reachable from the PC running the client.
"""
import argparse
import base64
import json
import os
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from data_layer import RiotClient, load_settings
from data_layer.config import PLATFORM_TO_REGION

LOCKFILES = (
    r"C:\Riot Games\League of Legends\lockfile",
    "/Applications/League of Legends.app/Contents/LoL/lockfile",
    str(Path.home() / "Games/league-of-legends/drive_c/Riot Games/League of Legends/lockfile"),
)
TERMINAL_STATES = {"watch", "incompatible", "lost", "unsupported", "failed"}


class Lcu:
    def __init__(self, lockfile):
        _name, _pid, port, password, protocol = Path(lockfile).read_text().strip().split(":")
        self.base = f"{protocol}://127.0.0.1:{port}"
        token = base64.b64encode(f"riot:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Accept": "application/json",
                        "Content-Type": "application/json"}
        # The LCU serves a self-signed cert on loopback only; skip verification for that one host.
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, headers=self.headers, method=method)
        try:
            with urlopen(req, context=self.ctx, timeout=15) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else None
        except HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw
        except URLError as e:
            return 0, str(e)


def find_lockfile(explicit):
    for candidate in (explicit, os.environ.get("LOL_LOCKFILE"), *LOCKFILES):
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit("Could not find the League client lockfile (is the client running?). "
             "Pass --lockfile <path> or set LOL_LOCKFILE.")


def probe_game(lcu, game_id, wait):
    status, body = lcu.request("GET", f"/lol-replays/v1/metadata/{game_id}")
    if status == 200 and isinstance(body, dict) and body.get("state") == "watch":
        return "already downloaded", body
    status, body = lcu.request("POST", f"/lol-replays/v1/rofls/{game_id}/download", {"componentType": "replay-button"})
    if status not in (200, 204):
        return f"download rejected (HTTP {status})", body
    deadline = time.time() + wait
    state, meta = "requested", None
    while time.time() < deadline:
        time.sleep(1)
        status, meta = lcu.request("GET", f"/lol-replays/v1/metadata/{game_id}")
        state = meta.get("state") if isinstance(meta, dict) else f"HTTP {status}"
        if state in TERMINAL_STATES:
            break
    return f"state={state}", meta


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("riot_id", help='e.g. "Reus#FIRST"')
    p.add_argument("--platform", default="euw1", choices=sorted(PLATFORM_TO_REGION))
    p.add_argument("-n", type=int, default=5, help="how many recent matches to probe")
    p.add_argument("--wait", type=int, default=60, help="seconds to wait for each download")
    p.add_argument("--lockfile")
    p.add_argument("--list-only", action="store_true", help="only list match IDs; don't touch the client")
    args = p.parse_args(argv)

    name, _, tag = args.riot_id.partition("#")
    if not tag:
        sys.exit('Riot ID must look like "Name#TAG"')
    settings = load_settings()
    client = RiotClient(settings.api_key, args.platform, PLATFORM_TO_REGION[args.platform])
    account = client.account_by_riot_id(name, tag)
    if not account:
        sys.exit(f"No account found for {args.riot_id}")
    ids = client.match_ids(account["puuid"], count=args.n)
    print(f"{args.riot_id} ({args.platform}): {len(ids)} recent matches")
    if args.list_only:
        print("\n".join(ids))
        return

    lcu = Lcu(find_lockfile(args.lockfile))
    status, path = lcu.request("GET", "/lol-replays/v1/rofls/path")
    print(f"Replay folder: {path if status == 200 else f'unknown (HTTP {status})'}")
    for match_id in ids:
        game_id = match_id.split("_", 1)[1]
        result, detail = probe_game(lcu, game_id, args.wait)
        print(f"{match_id}: {result}")
        if "watch" not in result and "already" not in result:
            print(f"    detail: {detail}")


if __name__ == "__main__":
    main()
