import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLATFORM_TO_REGION = {
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
    "kr": "asia", "jp1": "asia",
    "oc1": "sea", "sg2": "sea", "tw2": "sea", "vn2": "sea",
}


@dataclass(frozen=True)
class Settings:
    api_key: str
    platform: str
    region: str
    db_path: Path
    cache_dir: Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RIOT_API_KEY is not set; add it to .env (see .env.example)")
    platform = os.environ.get("RIOT_PLATFORM", "na1").lower()
    if platform not in PLATFORM_TO_REGION:
        raise RuntimeError(f"Unknown RIOT_PLATFORM {platform!r}")
    data_dir = Path(os.environ.get("TOOLKIT_DATA_DIR", ROOT / "data"))
    return Settings(
        api_key=api_key,
        platform=platform,
        region=PLATFORM_TO_REGION[platform],
        db_path=data_dir / "toolkit.db",
        cache_dir=data_dir / "cache",
    )
