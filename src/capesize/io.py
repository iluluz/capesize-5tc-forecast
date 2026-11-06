"""Locate the team workbooks (outside Git) and check them against data_manifest.csv."""
import hashlib
import os
import pathlib

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO / "data_manifest.csv"


def _load_dotenv() -> None:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def data_dir() -> pathlib.Path:
    _load_dotenv()
    return pathlib.Path(os.environ.get("CAPESIZE_DATA_DIR", REPO / "data" / "workbooks"))


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def check_manifest(folder: pathlib.Path | None = None) -> pd.DataFrame:
    """Return one row per manifest file with status ok / missing / hash mismatch."""
    folder = folder or data_dir()
    m = pd.read_csv(MANIFEST)
    status = []
    for name, expected in zip(m["file"], m["sha256"], strict=True):
        p = folder / name
        if not p.exists():
            status.append("missing")
        else:
            status.append("ok" if sha256(p) == expected.upper() else "hash mismatch")
    return m.assign(status=status)[["file", "version_date", "status"]]


if __name__ == "__main__":
    print(check_manifest().to_string(index=False))
