# Capesize 5TC forecasting: PortWatch and China customs data

Purpose: weekly dry bulk cargo-flow features (IMF PortWatch) and monthly China import mix (customs)
for forecasting the Capesize 5TC spot rate 4 weeks ahead.

## Data
| Dataset | Source | Frequency | Start | Release lag (assumed) | Status |
|---|---|---|---|---|---|
| Port calls and trade estimates, dry bulk | IMF PortWatch, ArcGIS REST `Daily_Ports_Data` | daily -> weekly | 2019-01 | calls 2 d, volumes 21 d | built: `outputs/3_...PortWatch_Weekly_Data.xlsx` |
| Chokepoint transits, dry bulk | IMF PortWatch, `Daily_Chokepoints_Data` | daily -> weekly | 2019-01 | 2 d | built (same workbook) |
| China imports by origin | China Customs platform (HS8, 2024-01 on) + UN Comtrade (2016-01..2023-12) | monthly | 2016-01 | 18 d after month end | built: `outputs/6_...China_Customs_Monthly.xlsx` |

PortWatch trade volumes are in metric tons (dataset description) and are shown in 10k t.

## Reproduce
1. `python -m venv .venv`, activate it, `pip install -r requirements.txt`
2. From `scripts/`, run in order:
   `pw_01_discover.py` -> `pw_02_select_ports.py` -> `pw_02b_write_selection.py` -> `pw_03_pull.py` ->
   `pw_04_weekly.py` -> `build_workbooks.py`
   Customs: place the platform exports in `data/raw/customs/` (steps in `MANUAL_STEPS.md`), then run
   `cu_01_fetch.py` (Comtrade, resumable) -> `cu_02_check_platform.py` -> `cu_03_build_workbook.py`.
3. Optional check: recalculate a copy of the workbook (LibreOffice or Excel) and run
   `verify_workbook.py <copy.xlsx>`.
4. Outputs appear in `outputs/`. Raw data (`data/raw/`) and intermediates (`data/interim/`) are not committed.

Pulls are resumable: each port/chokepoint is cached in `data/interim/cache/` as soon as it arrives, so
rerunning a script after a server error only fetches what is missing. The PortWatch server fails a large
share of requests at random (especially on its Tuesday update day); the scripts retry automatically.

To change which ports feed each role, edit `pw_02b_write_selection.py` and rerun it, `pw_04` and
`build_workbooks` (no re-download needed for ports already pulled).

## Caveats
- PortWatch dry bulk is not split by vessel size; trade volumes are AIS-derived estimates and are revised.
  The workbook holds the revised history, so backtests carry some look-ahead bias. Re-download weekly to
  build vintages.
- Guinea bauxite was dropped: PortWatch badly under-counts it (offshore transshipment is not captured as port activity).
  Bauxite flow is represented by Weipa (AU) and Trombetas (BR) only.
- Manual steps for the customs data (Wind / customs platform / Comtrade key) and the Git check: `MANUAL_STEPS.md`.
- Release lags are assumptions (editable yellow cells in the workbooks).
- Raw data is excluded from Git; PortWatch terms: https://www.imf.org/external/terms.htm
  (cite "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org)").
