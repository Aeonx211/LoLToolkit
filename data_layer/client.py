import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import Settings
from .ratelimit import BULK, LIVE, RateLimiter

# Riot enforces app limits per routing host; these are the key's app-wide limits.
DEFAULT_APP_LIMITS = ((20, 1.0), (100, 120.0))
USER_AGENT = "LoLInsightToolkit/0.1"


class RiotApiError(RuntimeError):
    def __init__(self, status, path, detail=""):
        hint = " (check RIOT_API_KEY)" if status in (401, 403) else ""
        super().__init__(f"Riot API returned {status} for {path}{hint}: {detail}")
        self.status = status


def _urllib_transport(url, headers):
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode("utf-8", "replace")
    except (URLError, TimeoutError) as e:
        return 0, {}, str(e)


class RiotClient:
    MAX_ATTEMPTS = 5

    def __init__(self, api_key, platform, region, app_limits=DEFAULT_APP_LIMITS,
                 bulk_reserve=0.2, transport=_urllib_transport, sleep=time.sleep):
        self._key = api_key
        self.platform = platform
        self.region = region
        self._app_limits = app_limits
        self._bulk_reserve = bulk_reserve
        self._transport = transport
        self._sleep = sleep
        self._limiters = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings):
        return cls(settings.api_key, settings.platform, settings.region)

    def _limiter(self, host):
        with self._lock:
            if host not in self._limiters:
                self._limiters[host] = RateLimiter(self._app_limits, self._bulk_reserve, sleep=self._sleep)
            return self._limiters[host]

    def _get(self, host, path, params=None, priority=BULK):
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"https://{host}{path}" + (f"?{urlencode(query)}" if query else "")
        headers = {"X-Riot-Token": self._key, "Accept": "application/json", "User-Agent": USER_AGENT}
        limiter = self._limiter(host)
        status, body = 0, ""
        for attempt in range(self.MAX_ATTEMPTS):
            limiter.acquire(priority)
            status, resp_headers, body = self._transport(url, headers)
            if status == 200:
                return json.loads(body)
            if status == 404:
                return None
            if status == 429:
                limiter.block_for(float(resp_headers.get("Retry-After", 2)))
                continue
            if status == 0 or status >= 500:
                self._sleep(min(2 ** attempt, 16))
                continue
            break
        raise RiotApiError(status, path, body[:200])

    @property
    def _regional(self):
        return f"{self.region}.api.riotgames.com"

    @property
    def _platform(self):
        return f"{self.platform}.api.riotgames.com"

    def account_by_riot_id(self, game_name, tag_line, priority=LIVE):
        path = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
        return self._get(self._regional, path, priority=priority)

    def account_by_puuid(self, puuid, priority=BULK):
        return self._get(self._regional, f"/riot/account/v1/accounts/by-puuid/{puuid}", priority=priority)

    def match_ids(self, puuid, count=20, start=0, queue=None, match_type=None, start_time=None, end_time=None,
                  priority=BULK):
        params = {"start": start, "count": count, "queue": queue, "type": match_type, "startTime": start_time,
                  "endTime": end_time}
        return self._get(self._regional, f"/lol/match/v5/matches/by-puuid/{puuid}/ids", params, priority) or []

    def match(self, match_id, priority=BULK):
        return self._get(self._regional, f"/lol/match/v5/matches/{match_id}", priority=priority)

    def timeline(self, match_id, priority=BULK):
        return self._get(self._regional, f"/lol/match/v5/matches/{match_id}/timeline", priority=priority)

    def active_game(self, puuid, priority=LIVE):
        return self._get(self._platform, f"/lol/spectator/v5/active-games/by-summoner/{puuid}", priority=priority)

    def summoner(self, puuid, priority=LIVE):
        return self._get(self._platform, f"/lol/summoner/v4/summoners/by-puuid/{puuid}", priority=priority)

    def league_entries(self, puuid, priority=LIVE):
        return self._get(self._platform, f"/lol/league/v4/entries/by-puuid/{puuid}", priority=priority) or []

    def champion_masteries(self, puuid, top=None, priority=BULK):
        if top:
            path = f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top"
            return self._get(self._platform, path, {"count": top}, priority) or []
        path = f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
        return self._get(self._platform, path, priority=priority) or []
