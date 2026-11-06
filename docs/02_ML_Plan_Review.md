# 02 · ML part: review of the Version 2 plan and a right-sized proposal

## 1. Verdict

The plan's direction is right: the target (log change of 5TC), FFA as feature and benchmark, LightGBM per
horizon, walk-forward validation with purge, conformal intervals. **As written it is too much for our
project.** It is a 40-week, 2–3 person programme that assumes paid AIS data, options data, route-level
hierarchical reconciliation, five deep-learning families and three economic backtests. Our DL effort is a
separate text branch (see 03), so the ML part should be one solid, leakage-free LightGBM pipeline with honest
baselines.

**Keep:** target definition, FFA-implied benchmark, LightGBM (point + quantile), walk-forward with purge and
embargo, Diebold–Mariano test against FFA, split-conformal 80% intervals, ablation by feature group.
**Cut or defer:** TFT, N-HiTS, PatchTST, DeepAR, Chronos/TimesFM, HMM regimes, VECM/regime switching,
MinT route reconciliation, option-implied volatility, paid AIS, FFA overlay trading, shadow mode.

## 2. What the five datasets cover

| File | Content | Frequency | Coverage | Covers plan group |
|---|---|---|---|---|
| 1 BCI182 spliced + FFA | 5TC (182 basis), C8/C9/C10/C14/C16, C3, C5; FFA curve M0–M+5, Q, Cal; FFA volume, OI | daily (OI weekly) | 5TC from 1999; routes & FFA **2014-05 → 2026-10** (~3,100 days) | A (FFA), B (spot dynamics), target |
| 2 Iron ore weekly | port inventory, hot metal, mill stocks, AU+BR shipments, BF utilisation | weekly | from 2005 | E (iron ore) |
| 3 PortWatch weekly | AU/BR iron ore exports, AU coal, bauxite, China port calls, Cape/Suez transits | weekly | **2019-01** → | C (free AIS proxy), E (tonne-miles) |
| 4 Fleet supply | fleet, deliveries, demolition, orderbook | monthly | long | F (supply) |
| 6 China customs | iron ore / coal / bauxite imports by origin, tonne-mile proxy | monthly | 2015-01 → 2026-09 | E (demand, long-haul share) |

Missing versus the plan: paid AIS (ballasters, cargo in transit, queues, speeds), option implied volatility,
coal/steel margin series, macro (FRED: free, easy to add later), text (handled in 03).

## 3. Proposed scope

### 3.1 Decision grid and point-in-time join
- **Grid:** Baltic trading days (London), 2014-05-06 → latest. Decision time = Baltic publication of S_t.
- **Join:** every non-daily feature enters on its **Estimated available date** (all workbooks have a
  Long Table with it), via `merge_asof(direction="backward")` on available date ≤ decision date. Never join
  on the reference period.
- **Unit test (gate G1):** for 20 random dates, assert every feature value was available before that date.

### 3.2 Targets
- Primary: `y_{t,h} = ln(S_{t+h} / S_t)`, **h = 5 and 20 trading days**, issued every trading day.
  h = 40/65 are stretch goals (few independent samples: ~12 and ~4 a year after overlap).
- Derived: direction class (rise / flat / fall at ±0.5 × rolling historical σ_h of y, using only past data).
- Stretch: next 1–3 calendar-month average vs the matching FFA contract.
- Noise-reduced variant (5-day average around t+h) as a robustness check only.

### 3.3 Baselines (must be beaten or matched)
1. Random walk: ŷ = 0.
2. Seasonal naïve: mean y_{h} of the same calendar week in past years (training window only).
3. **FFA-implied:** constant-maturity forward F_{t,h} interpolated from M0/M+1/M+2 at t+h;
   ŷ = ln(F_{t,h} / S_t). The benchmark that matters.
4. Small linear model: ridge on ~10 features (FFA basis, momentum, vol). Also a robust floor.

### 3.4 Main model
- **LightGBM, one model per horizon**: Huber objective for the point forecast; quantile objective at
  0.1/0.5/0.9; optional 3-class classifier.
- Shallow trees, strong regularisation (num_leaves 15–31, min_data_in_leaf ≥ 50, feature_fraction 0.7,
  early stopping on an inner time-ordered validation fold).
- Monotonic constraints only where obvious (e.g. FFA basis +).
- **Route panel (stretch):** routes are available from 2014, so a pooled panel (5TC + C8–C16 + C3/C5 with a
  route id) is possible later; skip MinT reconciliation.

### 3.5 Feature set (start ~50, select to ~25–35)

| Group | Features (from file) | Note |
|---|---|---|
| FFA (1) | basis M+1, M+2; slope ln(M+2/M+1); quarter structure; ln(Cal+1/spot); M+1 5-day change; OI 4-week change; volume/OI | strongest group |
| Spot dynamics (1) | ln(S_t/S_{t−k}) for k=5,20,60; deviation from 60/250-day mean; realised vol 20/60; C14 vs C10 relative strength; C3/C5 ratio; C16 < 0 flag | |
| Iron ore (2) | port inventory vs 5-yr same week; hot metal YoY; AU+BR shipments 4-wk YoY; inventory cover days | weekly, lagged by release |
| PortWatch (3) | AU+BR exports 4-wk YoY; Brazil share; China port calls 4-wk; Cape share 4-wk | **from 2019 only** → NaN before + `portwatch_available` flag (plan 3.4) |
| Fleet (4) | net growth 12m; orderbook/fleet; deliveries next 12m share | slow, matters at h=20+ |
| Customs (6) | iron ore imports 3-mo YoY; Brazil share; bauxite Guinea share; tonne-mile YoY | 20-day lag (+28 for January) |
| Calendar | annual Fourier (2 pairs); days to Chinese New Year; month-end/quarter-end | |

Transformations: only past-window z-scores, log differences, 1/2/4-week lags. Drop one of any pair with
|corr| > 0.9 (decided inside each training window).

### 3.6 Validation
- **Walk-forward, expanding window, refit monthly**, test 2019-01 → latest (PortWatch era; ~1,950 test
  days). Report 2016–2018 as an extra test without PortWatch features if time allows.
- **Purge h and embargo h** trading days between train and test (overlapping targets).
- Hyper-parameters by a small grid inside the training window only.
- **Conformal:** split-conformal on the last 12 months of each training window → 80% interval.

### 3.7 Metrics and tests
- Point: MAE, RMSE of y; Theil's U vs random walk (must be < 1).
- Direction: hit rate, 3-class F1, Pesaran–Timmermann test.
- Distribution: pinball loss, 80% coverage (target 75–85%).
- **vs FFA:** Diebold–Mariano with HAC variance (h−1 lags), per horizon; also "FFA + ML" combination
  test (ridge on [ŷ_FFA, ŷ_ML]).
- Sub-periods: calm vs high-volatility (top quintile of 20-day realised vol).
- **Ablation:** −FFA, −spot dynamics, −PortWatch, −fundamentals (2/4/6). One table, one paragraph.

### 3.8 Gates (adapted from the plan)
| Gate | Pass condition |
|---|---|
| G1 data | point-in-time join test passes; no NaN in target; grid matches Baltic days |
| G2 baselines | RW, seasonal, FFA-implied, ridge evaluated on the same walk-forward |
| G3 model | LightGBM Theil's U < 1 at h=5 and h=20, and not significantly worse than FFA (DM) |
| G4 freeze | "best ML" tagged in Git (`ml-v1.0`), OOS predictions exported for the text branch |

## 4. Interface to the text branch (must be ready at G4)
`data/processed/ml_oos_predictions.parquet`, one row per (date, h):
`date, h, y_true, yhat, q10, q50, q90, model_version, train_end`.
Predictions inside the text-event window must be **out-of-sample** (walk-forward), never in-sample fits.

## 5. Known limitations to state in the report
- Several inputs are revised histories (PortWatch, Clarksons, customs final data), not first releases:
  some look-ahead bias remains; release lags only partly correct it.
- PortWatch starts 2019, so its contribution is measured on 2019+ only.
- 5TC is a smoothed assessment; daily changes are autocorrelated, which inflates naive accuracy at h=1.
- The 2026 index change (BCI182) is handled by the teammates' splice; splice errors enter the labels.

## 6. Work packages and rough timing (2–3 people)
| Week | Package | Output |
|---|---|---|
| 1 | Calendar, loaders, point-in-time feature store, targets, G1 tests | `features.parquet` |
| 2 | Walk-forward splitter, baselines incl. FFA-implied, metrics, DM test | baseline table (G2) |
| 3–4 | LightGBM point + quantile, conformal, feature selection | model table (G3) |
| 5 | Ablations, sub-periods, freeze and export OOS predictions | `ml-v1.0`, predictions (G4) |
| 6 | Write-up of the ML part | report section |

Also before starting: replace the old `3_Capesize_5TC_PortWatch_Weekly_Data.xlsx` in the shared folder with
the final one from `capesize-5tc/outputs/` (the old file still has the dropped Guinea series).
