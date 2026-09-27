import json
import ssl
from urllib.request import urlopen

# The game client serves this on localhost with a self-signed certificate while you're in a game.
LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"


def fetch_live_client(timeout=1.5):
    """Current items/levels from the local League client, or None when no game is running on this machine."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(LIVE_CLIENT_URL, timeout=timeout, context=context) as resp:
            return json.load(resp)
    except (OSError, ValueError):
        return None


def current_state_by_riot_id(data):
    out = {}
    for p in (data or {}).get("allPlayers", []):
        riot_id = f'{p.get("riotIdGameName", p.get("summonerName", "?"))}#{p.get("riotIdTagLine", "")}'
        out[riot_id.lower()] = {
            "level": p.get("level"),
            "items": [i.get("displayName") for i in p.get("items", [])],
            "scores": p.get("scores", {}),
        }
    return out
