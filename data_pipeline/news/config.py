"""Settings for the news pipeline. Contract values (cutoff, date-only time) come from capesize.contract."""
import os
from datetime import date
from pathlib import Path

from capesize.contract import DATE_ONLY_TIME_UTC, NEWS_CUTOFF_UTC  # noqa: F401  (re-exported for convenience)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    """Read KEY=VALUE lines from the repo's .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(REPO_ROOT / ".env")

# Local data folder (gitignored). Text-branch files follow docs/03 §5.
LOCAL_DIR = Path(os.getenv("CAPESIZE_LOCAL_DIR", REPO_ROOT / "data")).expanduser()
RAW_DIR = LOCAL_DIR / "raw" / "news"          # scraper output, one folder per source
CACHE_DIR = LOCAL_DIR / "cache" / "news"      # downloaded pages, so crashed runs resume
LOG_DIR = LOCAL_DIR / "logs"
TEXT_DIR = LOCAL_DIR / "text"                 # headlines.parquet, headlines_clean.parquet
PROCESSED_DIR = LOCAL_DIR / "processed"       # text_daily_features.parquet (later)

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
USER_AGENT = (
    "CapesizeNewsResearch/1.0 (MIT 15.071 course project; academic research; "
    f"contact: {CONTACT_EMAIL or 'not-set'})"
)

# Collection range: a superset of every window still under discussion (decisions.md O2),
# starting about T0 - 7 months for lookback features. The modelling window is cut later.
COLLECTION_START = date(2025, 8, 1)

REQUEST_DELAY_SECONDS = 3.0
MAX_RETRIES = 3
MIN_HEADLINES_PER_DAY = 5   # volume check, docs/03 §2
