# capesize-5tc-forecast

Forecasting the Capesize 5TC spot rate (Baltic Exchange) with a tabular ML model, plus a text (DL) branch that
uses news around the 2026 Strait of Hormuz closure.

> **This repository is public. No data in Git:** no workbooks, no price series, no licensed text, no numbers
> copied from licensed sources. Data lives on the team's shared drive; `data_manifest.csv` records each file's SHA-256.

## Layout

```
├─ src/capesize/            shared code
│  ├─ contract.py           horizons, news cutoff, ... (mirrors docs/decisions.md)
│  ├─ calendar.py           trading-day grid, news-window assignment (12:00 UTC cutoff)
│  ├─ targets.py            y = ln(S_{t+h}/S_t), residual target for the text branch
│  ├─ splits.py             walk-forward splits with purge (+ optional embargo)
│  ├─ io.py                 locate workbooks, check them against data_manifest.csv, save/load tables
│  ├─ config.py             ML paths and run settings (test start, embargo, FFA lag)
│  ├─ data.py · pit.py      workbook loaders · point-in-time join (strict: available < decision date)
│  ├─ features.py           feature store on the trading-day grid (FFA, spot, iron ore, PortWatch, fleet, customs, calendar)
│  ├─ checks.py             gate G1 checks (PIT vs brute force, negative control, targets, grid)
│  ├─ baselines.py          random walk, seasonal naive, FFA-implied, ridge
│  ├─ models.py             LightGBM point (Huber) + quantiles + conformal interval, ablation groups
│  ├─ validation.py         walk-forward runner (monthly refit, purge h + embargo h)
│  ├─ metrics.py            Theil's U, Diebold-Mariano (HAC), Pesaran-Timmermann, 3-class F1
│  ├─ evaluation.py         runners, metrics tables, FFA+ML combination, encompassing test, export
│  ├─ features_v2.py · regime.py · macro.py   v1.1 feature groups (FFA bias, curve, routes, path, utilisation, Markov regime, FRED)
│  ├─ stats_models.py       VECM (spot + FFA curve), ARMA
│  ├─ ensemble.py           equal-weight / inverse-MSE / stacking ensembles, ACI intervals
│  ├─ panel.py · products.py · foundation.py   route panel · turning points, monthly vs FFA, backtests · Chronos (optional)
├─ notebooks/01_ml_pipeline.ipynb   runs G1 -> G4 end to end (outputs stripped before commit)
│                                   + direction classifier, 2016-18 extra test, h=40/65; writes outputs/reports/ML_results.md
├─ tests/                   pytest; run before every PR (CI runs them too)
├─ data_pipeline/portwatch_customs/   pipeline that built workbooks 3 (PortWatch) and 6 (China customs)
├─ experiments/results.csv  one row per model run (append, never edit old rows)
├─ docs/                    01 repo setup · 02 ML plan · 03 DL text branch · 04 ML v1.1 hand-over · decisions.md
├─ data_manifest.csv        file, date, bytes, SHA-256, source, licence note
└─ data/  (gitignored)      local copy of the shared drive
```

Planned (add in PRs): `src/capesize/text/` (text branch).

ML outputs (gitignored): `data/processed/` (feature store, OOS predictions, `ml_oos_predictions.parquet` for the text
branch) and `outputs/tables/`, `outputs/figures/`.

**Current ML release: `ml-v1.1`** (tag). Text branch: read [docs/04_ML_v1.1_Handover.md](docs/04_ML_v1.1_Handover.md).
`ml-v1.0` remains tagged; its predictions are kept as `ml_oos_predictions_v1.0.parquet`.

## Setup

```powershell
git clone https://github.com/iluluz/capesize-5tc-forecast.git
cd capesize-5tc-forecast
python -m venv .venv
.venv\Scripts\activate                # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt       # text branch: also requirements-dl.txt; Chronos runs: requirements-fm.txt
pip install -e .
copy .env.example .env                # then set CAPESIZE_DATA_DIR to your local copy of the workbooks
python -m capesize.io                 # every workbook should say "ok"
pytest
```

`missing` or `hash mismatch` from `python -m capesize.io` means your copy is not the version in the manifest.
Get the current file from the shared drive.

## How we work

- One issue → one branch (`feat/…`, `fix/…`, `data/…`, `docs/…`) → one pull request into `main`.
- PR description: what changed, how it was checked. Tests must pass.
- Changing anything in `docs/decisions.md` / `contract.py` needs approval from both the ML and the text-branch owner.
- Every model run appends a row to `experiments/results.csv`, failed runs included.
- Notebooks: run `nbstripout --install` once, so outputs (which can contain data) never reach Git.

## Data

| File | Content | Coverage |
|---|---|---|
| 1 | 5TC, routes C3/C5/C8–C16, FFA curve, volume, open interest | routes and FFA from 2014-05 |
| 2 | iron ore weekly (port stocks, hot metal, AU+BR shipments) | from 2005 |
| 3 | PortWatch weekly (port exports, China calls, chokepoints) | from 2019 |
| 4 | fleet supply monthly | long history |
| 6 | China customs imports by origin (iron ore, coal, bauxite) | 2015-01 → 2026-09 |
