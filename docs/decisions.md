# Decisions log (shared contract)

Rules: one row per decision. A change to any **contract** item needs a PR that edits this file and
`src/capesize/contract.py` together, approved by the ML owner and the text-branch owner.
Status: **PROPOSED** (written down, not yet agreed) · **AGREED** (date + who) · **OPEN** (conflicting proposals).

## Contract items

| # | Item | Value | Status | Source |
|---|---|---|---|---|
| C1 | Calendar | Baltic trading days (London); one row per trading day t | PROPOSED | 02 §3.1, 03 §1 |
| C2 | Decision time | Baltic publication of S_t (~13:00 London) | PROPOSED | 03 §1 |
| C3 | News cutoff | 12:00 UTC on day t; window (12:00 UTC previous trading day, 12:00 UTC day t]; weekend/holiday news rolls forward | PROPOSED (same in both DL proposals) | 03 §1, DL workstream plan §3 |
| C4 | Timestamps | UTC; date-only items at 23:59:59 UTC; first-seen time, not later edits | PROPOSED | 03 §1 |
| C5 | ML horizons | h = 5 and h = 20 trading days, issued every trading day | **OPEN**: which is primary (see O3) | 02 §3.2 |
| C6 | ML target | y = ln(S_{t+h}/S_t), 5TC 182 basis from workbook 1 | PROPOSED | 02 §3.2 |
| C7 | ML → DL hand-over | out-of-sample walk-forward predictions only: `ml_oos_predictions.parquet` (`date, h, y_true, yhat, q10, q50, q90, model_version, train_end`) | PROPOSED | 02 §4 |
| C8 | Point-in-time join | non-daily features enter on their estimated available date (`merge_asof` backward) | PROPOSED | 02 §3.1 |
| C9 | Validation | expanding walk-forward, monthly refit, purge h trading days | PROPOSED | 02 §3.6 |

## Open items (need a team decision)

Two DL proposals exist: `docs/03_DL_Text_Branch_Design.md` and the DL workstream plan
(`DL_Workstream_Plan_Hormuz_News.md`, shared folder, not in this public repo because it quotes licensed price values).

| # | Question | Option A (03) | Option B (DL workstream plan) |
|---|---|---|---|
| O1 | DL target | residual of the ML 5TC forecast (text corrects ML) | Hormuz flow index (PortWatch transits / baseline), next 7 days; its output becomes one "Hormuz stress score" feature for the ML 20-day model |
| O2 | T0 and window | T0 = closure date (from sources); window T0 ± 6 months | T0 data-defined (7-day transits < 50% of baseline); fixed window 2025-09-01 → 2026-08-31 |
| O3 | Primary ML horizon | h = 5 (more independent test windows) | 4 weeks (h = 20), matching the chartering-manager decision |
| O4 | Timeline | 02 §6 assumes ~6 weeks | project due **2026-11-20** (per DL workstream plan) [verify]: the ML plan must shrink to ~2 weeks |
| O5 | News corpus | GDELT + official releases | pilot of JMIC/UKMTO, RavenPack (WRDS), Wind/Choice/iFinD, Media Cloud, GDELT; pick by rubric |

## Log

| Date | Decision | Who |
|---|---|---|
| 2026-11-05 | Repository created (public), data kept out of Git, manifest with SHA-256 | repo owner |
| 2026-11-07 | ML: FFA inputs use the previous assessment (`config.FFA_LAG = 1`). BFA curves publish ~17:30 London, after the 13:00 decision time (C2); same-day FFA flattered h=5 results (FFA-implied U 1.047 → 1.127 when lagged). Text branch: news windows unaffected. | ML owner (iluluz) |
| 2026-11-07 | ML: walk-forward uses embargo = h on top of the purge (training stops 2h rows before each test month); inner validation = 3 time-ordered folds of 250 rows, each after an h-row purge. | ML owner (iluluz) |
| 2026-11-08 | ML extras (not used for model choice): 3-class direction classifier; extra test 2016–2018 without PortWatch (inner validation falls back to 3 shorter blocks when the window is too short for 3×250 rows); stretch h = 40/65 with an M+3 node in the FFA-implied forecast. Main h = 5/20 results unchanged. Text branch: `data/processed/baltic_5tc_trading_days.csv` (5TC publication dates, dates only) for the news-window merge. | ML owner (iluluz) |
| 2026-11-08 | **G4 freeze `ml-v1.0`**: main ML = `ens_ridge_lgbmres` (equal-weight ridge + LightGBM on the FFA residual, interval from the LightGBM-residual CQR). Passes G3 at h = 5 and 20. Ridge had the lower 2019–2022 mean U (0.911 vs 0.923) but has no quantiles (needed by C7); reported as the linear benchmark. `ml_oos_predictions.parquet` exported with `model_version = ml-v1.0`; metrics in `experiments/results.csv`. | ML owner (iluluz) |
| 2026-11-10 | **ML `ml-v1.1` tagged**: equal-weight ridge + VECM + `lr_path` (LightGBM on the FFA residual with path features), interval = `lr_path` quantiles shifted + ACI. Passes the pre-registered threshold vs v1.0 (2019–22 mean U 0.909 vs 0.923, 2023–26 0.861 vs 0.866, DM h=5 p<0.001, h=20 equal). The rule winner (same + Chronos-2, 0.900) was not released: possible pre-training overlap with the test years (02 leakage rule), and worse in 2026 (0.965 vs 0.950); this choice was made after seeing 2026 and is reported as such. `ml_oos_predictions.parquet` now holds `ml-v1.1`; v1.0 kept as `ml_oos_predictions_v1.0.parquet`. **Text branch switches to v1.1 after the DL owner confirms** (03 row 7 still says v1.0 until then). Hand-over: docs/04_ML_v1.1_Handover.md. | ML owner (iluluz) |
