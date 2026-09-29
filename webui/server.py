import json
import mimetypes
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import tuning
from build_sim import breakpoints, compare, run_scenario
from build_sim.data import GameData
from build_sim.effects import KEYSTONES, MINOR_RUNES, SHARDS
from build_sim.kits import KITS
from causal_analysis import analyze_match_id, analyze_puuid
from causal_analysis.__main__ import QUEUES
from data_layer import DataDragon, DataLayer, RiotApiError, load_settings
from live_advisor import build_report, resolve_roster

STATIC = Path(__file__).resolve().parent / "static"
EXAMPLES = Path(__file__).resolve().parent.parent / "build_sim" / "builds"
MAX_BODY = 1_000_000
JOB_TTL_S = 3600
PREDICTION_DEPTH = 5  # earlier games per player used (and fetched if missing) for the pre-game impact prediction


class App:
    def __init__(self):
        tuning.apply()
        settings = load_settings()
        self.layer = DataLayer.from_env()
        self.dd = DataDragon(settings.cache_dir)
        self.platform = settings.platform
        self.game = GameData(settings.cache_dir)
        self.jobs = {}
        self._lock = threading.Lock()

    # --- jobs ----------------------------------------------------------------------------------------------

    def start_job(self, tool, params):
        runner = {
            "player": self.run_player,
            "match": self.run_match,
            "advisor": self.run_advisor,
            "sim_run": self.run_sim,
            "sim_compare": self.run_compare,
            "sim_breakpoints": self.run_breakpoints,
        }.get(tool)
        if runner is None:
            raise ValueError(f"Unknown tool {tool!r}")
        job = {"id": uuid.uuid4().hex, "tool": tool, "status": "running", "progress": [], "partial": [],
               "result": None, "error": None, "started": time.time()}
        with self._lock:
            now = time.time()
            self.jobs = {k: j for k, j in self.jobs.items() if now - j["started"] < JOB_TTL_S}
            self.jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job, runner, params), daemon=True).start()
        return job["id"]

    def _run(self, job, runner, params):
        try:
            job["result"] = runner(params, job)
            job["status"] = "done"
        except (LookupError, ValueError, RiotApiError) as e:
            job["error"] = str(e.args[0]) if e.args else str(e)
            job["status"] = "error"
        except Exception as e:  # surface anything unexpected in the UI instead of a silent hang
            traceback.print_exc()
            job["error"] = f"{type(e).__name__}: {e}"
            job["status"] = "error"

    def get_job(self, job_id):
        with self._lock:
            return self.jobs.get(job_id)

    # --- tools ---------------------------------------------------------------------------------------------

    @staticmethod
    def _int(params, key, default, lo, hi):
        value = int(params.get(key) or default)
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
        return value

    def run_player(self, params, job):
        riot_id = str(params.get("riot_id", "")).strip()
        count = self._int(params, "count", 10, 1, 50)
        queue = int(params["queue"]) if params.get("queue") else None
        job["progress"].append(f"Looking up {riot_id}")
        puuid = self.layer.resolve_riot_id(riot_id)

        def on_result(result):
            # TODO: sends the full analysis (~9KB/game incl. rolling-impact timeline) to the browser and into its
            #  cache; slimming only saved ~2KB/game (measured), so not worth the complexity while thresholds are
            #  still being tuned. Revisit if the browser cache (5-10MB/origin) becomes a real constraint.
            job["partial"].append(result)
            job["progress"].append(f"Analyzed {result['match_id']} ({len(job['partial'])}/{count})")

        analyze_puuid(self.layer, puuid, count, queue, on_result=on_result)
        return {"puuid": puuid, "results": job["partial"], "rollup": self.layer.store.get_rollup(puuid)}

    def run_match(self, params, job):
        match_id = str(params.get("match_id", "")).strip()
        result = analyze_match_id(self.layer, match_id)
        if result is None:
            raise LookupError(f"Match {match_id} not found")
        if "skipped" in result:
            return result
        # Predicted impact: what each player's earlier games say they'd average. Not part of the cached analysis.
        # Only uses what's stored, unless the user asked to load history (a slow one-time fetch per match).
        load = bool(params.get("load_history"))
        players = []
        for i, p in enumerate(result["players"], 1):
            avg, games = self.layer.store.prior_impact(p["puuid"], result["game_start"], PREDICTION_DEPTH)
            if load and games < PREDICTION_DEPTH:
                job["progress"].append(f"Loading earlier games for {p['riot_id']} ({i}/{len(result['players'])})")
                try:
                    analyze_puuid(self.layer, p["puuid"], PREDICTION_DEPTH, end_time=result["game_start"] // 1000 - 1)
                except RiotApiError as e:
                    job["progress"].append(f"Couldn't load history for {p['riot_id']}: {e}")
                avg, games = self.layer.store.prior_impact(p["puuid"], result["game_start"], PREDICTION_DEPTH)
            players.append({**p, "predicted_impact": None if avg is None else {"value": round(avg, 2), "games": games}})
        return {**result, "players": players, "prediction_depth": PREDICTION_DEPTH}

    def run_advisor(self, params, job):
        riot_id = str(params.get("riot_id", "")).strip()
        depth = self._int(params, "depth", 8, 1, 30)
        replay = str(params.get("replay") or "").strip() or None
        roster = resolve_roster(self.layer, self.dd, riot_id, replay)
        report = build_report(self.layer, self.dd, roster, depth,
                              progress=job["progress"].append, on_player=job["partial"].append)
        report["my_team"] = roster.my_team
        report["roster"] = [vars(p) for p in roster.players]
        return report

    def run_sim(self, params, job):
        return run_scenario(self.game, params["scenario"])

    def run_compare(self, params, job):
        a, b = compare(self.game, params["scenario"], params["build_b"])
        return {"a": a, "b": b}

    def run_breakpoints(self, params, job):
        candidates = params.get("candidates") or None
        base, rows = breakpoints(self.game, params["scenario"], candidates)
        return {"base": base, "rows": rows}

    # --- metadata ------------------------------------------------------------------------------------------

    def champion_names(self):
        """Riot's internal champion ids to display names (MonkeyKing -> Wukong). Empty if Data Dragon is unreachable."""
        try:
            return {c["id"]: c["name"] for c in self.dd.champions().values()}
        except OSError:
            return {}

    def meta(self):
        examples = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(EXAMPLES.glob("*.json"))
                    if "attacker" in p.read_text(encoding="utf-8")}
        return {
            "platform": self.platform,
            "queues": {str(k): v for k, v in QUEUES.items()},
            "champions": self.champion_names(),
            "sim": {
                "champions": {name: list(kit.abilities) for name, kit in KITS.items()},
                "keystones": sorted(k for k in KEYSTONES if k),
                "minor_runes": sorted(MINOR_RUNES),
                "shards": sorted(SHARDS),
                "items": sorted(i.name for i in self.game.items().values()),
                "examples": examples,
            },
        }


class Handler(BaseHTTPRequestHandler):
    app: App = None
    allowed_hosts: set = set()

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        # Refuse requests addressed to other hostnames (DNS rebinding protection for a localhost-only tool).
        return self.headers.get("Host", "") in self.allowed_hosts

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/static/"):
            file = (STATIC / path.removeprefix("/static/")).resolve()
            if STATIC in file.parents and file.is_file():
                ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                return self._send(200, file.read_bytes(), ctype)
            return self._send(404, {"error": "not found"})
        if path == "/api/meta":
            return self._send(200, self.app.meta())
        if path == "/api/tuning":
            return self._send(200, tuning.describe())
        if path.startswith("/api/jobs/"):
            job = self.app.get_job(path.removeprefix("/api/jobs/"))
            if job is None:
                return self._send(404, {"error": "job not found"})
            return self._send(200, job)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        # Requiring JSON means other websites can't post here without a CORS preflight, which we never grant.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(415, {"error": "expected application/json"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/jobs":
                return self._send(200, {"id": self.app.start_job(body.get("tool"), body.get("params") or {})})
            if path == "/api/tuning":
                tuning.update(body.get("values") or {})
                return self._send(200, tuning.describe())
            if path == "/api/tuning/reset":
                tuning.reset(body.get("keys"))
                return self._send(200, tuning.describe())
            return self._send(404, {"error": "not found"})
        except (ValueError, KeyError) as e:
            return self._send(400, {"error": str(e.args[0]) if e.args else str(e)})


def serve(port=8765, open_browser=False):
    Handler.app = App()
    Handler.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"LoL Insight Toolkit running at {url}  (Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
