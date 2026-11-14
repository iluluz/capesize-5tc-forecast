"""Paths and run settings for the ML part. Shared-contract values (horizons) live in contract.py."""
import pathlib

from capesize.contract import HORIZONS
from capesize.io import REPO, data_dir

PROCESSED = REPO / "data" / "processed"
TABLES = REPO / "outputs" / "tables"
FIGURES = REPO / "outputs" / "figures"

GRID_START = "2014-05-06"      # first FFA curve date = first decision date
STRETCH_HORIZONS = (40, 65)
TEST_START = "2019-01-01"       # PortWatch era
PURGE_MULT = 1                  # purge = PURGE_MULT * h trading days
EMBARGO_MULT = 1                # embargo = EMBARGO_MULT * h trading days (on top of the purge)
MIN_TRAIN = 250

# FFA (Baltic Forward Assessments) are published ~17:30 London, the 5TC index ~13:00 London (decision time,
# decisions.md C2). FFA_LAG = 1 uses yesterday's curve (strictly available at decision time);
# FFA_LAG = 0 uses today's close (a few hours of look-ahead). Agreed 2026-11-07: FFA_LAG = 1 (docs/decisions.md log).
FFA_LAG = 1

__all__ = ["HORIZONS", "workbook"]


def workbook(n: int) -> pathlib.Path:
    """Locate workbook n (1, 2, 3, 4, 6). Accepts both '1.Capesize_…' and '1_Capesize_…' file names."""
    hits = sorted(p for p in data_dir().glob(f"{n}[._]Capesize_5TC_*.xlsx") if not p.name.startswith("~$"))
    if len(hits) != 1:
        raise FileNotFoundError(f"expected one workbook {n} in {data_dir()}, found {[h.name for h in hits]}")
    return hits[0]
