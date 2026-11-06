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
