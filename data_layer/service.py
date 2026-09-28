from .client import RiotClient
from .config import load_settings
from .ratelimit import BULK, LIVE
from .store import Store


class DataLayer:
    """Single entry point the tools use: API calls go through the rate-limited client, results are cached in the store."""

    def __init__(self, client: RiotClient, store: Store):
        self.client = client
        self.store = store

    @classmethod
    def from_env(cls):
        settings = load_settings()
        return cls(RiotClient.from_settings(settings), Store(settings.db_path))

    def resolve_riot_id(self, riot_id, priority=LIVE):
        game_name, sep, tag_line = riot_id.rpartition("#")
        if not sep or not game_name or not tag_line:
            raise ValueError(f"Riot ID must look like Name#TAG, got {riot_id!r}")
        cached = self.store.find_account(game_name, tag_line)
        if cached:
            return cached
        account = self.client.account_by_riot_id(game_name, tag_line, priority)
        if account is None:
            raise LookupError(f"No Riot account found for {riot_id}")
        self.store.save_account(account["puuid"], account["gameName"], account["tagLine"])
        return account["puuid"]

    def recent_match_ids(self, puuid, count=20, queue=None, start=0, end_time=None, priority=BULK):
        """end_time is epoch seconds; only matches that started before it are returned."""
        return self.client.match_ids(puuid, count=min(count, 100), start=start, queue=queue, end_time=end_time,
                                     priority=priority)

    def game_pick(self, match_id, puuid, priority=BULK):
        """(champion, role) a player used in a match. Fetches the match without its timeline, and remembers everyone's."""
        pick = self.store.get_pick_info(match_id, puuid)
        if pick:
            return pick
        match = self.client.match(match_id, priority)
        if match is None:
            return None
        self.store.save_picks(match)
        return self.store.get_pick_info(match_id, puuid)

    def match_with_timeline(self, match_id, priority=BULK):
        cached = self.store.get_match(match_id)
        if cached:
            return cached
        match = self.client.match(match_id, priority)
        if match is None:
            return None
        timeline = self.client.timeline(match_id, priority)
        if timeline is None:
            return None
        self.store.save_match(match, timeline)
        return match, timeline
