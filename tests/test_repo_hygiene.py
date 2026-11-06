"""Guards for a public repository: manifest format, and no data files tracked."""
import pathlib
import subprocess

import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
BLOCKED = (".xlsx", ".xls", ".xlsm", ".parquet", ".pdf", ".doc", ".docx", ".zip", ".pkl", ".pt")


def test_manifest_format():
    m = pd.read_csv(REPO / "data_manifest.csv")
    assert {"file", "sha256", "licence_note"} <= set(m.columns)
    assert m["sha256"].str.fullmatch(r"[0-9A-Fa-f]{64}").all()


def test_no_data_files_tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return  # not a git checkout (e.g. zip download)
    files = out.splitlines()
    bad = [f for f in files if f.lower().endswith(BLOCKED) or f.split("/")[0] == "data" or "/data/" in f]
    assert not bad, f"data files tracked in Git: {bad}"
