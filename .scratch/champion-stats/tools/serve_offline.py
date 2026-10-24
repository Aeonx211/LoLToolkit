"""Start the web UI with Data Dragon stubbed out (the cloud container can't reach it)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import data_layer.ddragon as dd
dd._fetch = lambda url: ["15.19.1"] if url.endswith("versions.json") else {"data": {}}
from webui.server import serve
serve(int(sys.argv[1]))
