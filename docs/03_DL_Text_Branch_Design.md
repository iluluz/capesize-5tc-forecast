# 03 · DL part: text branch for the Strait of Hormuz closure window

Question: around the Strait of Hormuz closure, does a deep-learning text branch built on news headlines
improve the frozen best ML forecast of the Capesize 5TC rate (and C3/C5)?
Input: text. Output: a number (a correction to the ML forecast, plus quantiles).

---

## 1. Shared contract between the ML part and the text part (agree and record in `docs/decisions.md`)

| # | Item | Proposal | Reason |
|---|---|---|---|
| 1 | Calendar | Baltic trading days (London holidays). One row per trading day t. | The target only exists on these days. |
| 2 | Decision time | Publication of S_t by the Baltic Exchange (~13:00 London). | Same as the ML part. |
| 3 | **News cutoff** | **12:00 UTC on day t.** Window W_t = (12:00 UTC of the previous trading day, 12:00 UTC of day t]. Weekend and holiday news rolls into the next trading day. | 12:00 UTC is before 13:00 London in both GMT (13:00 UTC) and BST (12:00 UTC), so no headline can postdate S_t. |
| 4 | Timestamps | Store everything in UTC. Items with a date but no time → 23:59:59 UTC of that date (so they fall into the next day's window). Use the **first-seen** time; ignore later edits. | Conservative; prevents leakage. |
| 5 | **Horizon** | **Primary h = 5 trading days (1 week); secondary h = 20 (≈4 weeks).** Both issued **every trading day** ("4 weeks ahead, updated daily" = h=20). h = 1 only as a diagnostic. | Must equal the ML horizons. Next-day 5TC changes are small and autocorrelated (smoothed assessment), so a 1-day target mostly measures noise; news effects on freight play out over days to weeks. |
| 6 | Target | y_{t,h} = ln(S_{t+h}/S_t) — identical formula and source column (file 1, 5TC 182 basis). Text model learns the **ML residual** r_{t,h} = y_{t,h} − ŷ^{ML}_{t,h}. Final forecast ŷ = ŷ^{ML} + g(text). | Uses the ML forecast as the base; the text branch only adds information. |
| 7 | ML inputs to DL | Only **out-of-sample** walk-forward ML predictions (`ml_oos_predictions.parquet`, see 02 §4) from the frozen `ml-v1.0`. | In-sample ML fits would make the residual artificially small. |
| 8 | Event window | T0 = closure date (**team to fill in, with source**). Window = [T0 − 6 months, T0 + 6 months] ≈ 250 trading days. Collect text from T0 − 7 months for lookback features. | |
| 9 | Splits | Chronological. Proposal: train T0−6m … T0+1m; validation T0+1m … T0+2m; test T0+2m … T0+6m. Purge h days at each boundary. Optionally refit weekly on an expanding window inside the period. | The test must contain post-closure days the model has not seen; the training data must contain some post-closure days, or the model cannot learn the event regime. |
| 10 | Units/IDs | Dates as `YYYY-MM-DD` (trading day), h as integer days, routes `5TC`, `C3`, `C5`. | Simple joins. |

**Answer to the teammate's question:** yes to a 12:00 UTC cutoff. On the horizon: issue a forecast every
business day at both horizons, with h = 5 as the main metric and h = 20 (4 weeks ahead, updated daily) as the
second. Do not use next-business-day as the main horizon.

## 2. Text data

- **Sources (free, timestamped):** GDELT 2.0 (DOC API / GKG: global news with UTC timestamps and URLs);
  official releases (port authorities, IMO, US/UK maritime advisories, BIMCO news, miners' press releases).
  Paywalled outlets (Lloyd's List, TradeWinds) only if the team already has a licence; no scraping behind
  logins. Keep **headline + first sentence** where the licence permits; store URLs for traceability.
- **Query terms:** Hormuz, Persian Gulf, Iran, tanker, shipping, freight, dry bulk, Capesize, iron ore,
  Vale, BHP, Rio Tinto, Simandou, Red Sea, Suez, bunker, war risk insurance, port congestion, China steel.
- **Schema** (`data/text/headlines.parquet`): `id, published_utc, first_seen_utc, source, url, title,
  lead, lang, query, retrieved_utc`.
- **Cleaning:** English only (or a multilingual encoder); drop exact and near duplicates (cosine > 0.92 on
  embeddings); relevance filter (keyword or zero-shot classifier score); assign each item to W_t.
- **Volume check:** report headlines per day; flag days with fewer than N (e.g. 5) items.

## 3. How text becomes a number (methods, from safest to most ambitious)

### M1 — Frozen encoder + daily pooling + ridge (baseline, must be built)
1. Encode each headline with a **frozen** sentence encoder (e.g. `all-MiniLM-L6-v2`, `bge-small-en`, or
   FinBERT's [CLS]) → vector of 384/768 dimensions.
2. Daily aggregate per W_t: mean vector, headline count, and EWMA over 1/5/20 days.
3. PCA to ~16 dimensions **fitted on the training split only**.
4. Ridge regression (or LightGBM) on the PCA features → r̂_{t,h}.

### M2 — Interpretable scores (features, also useful for explaining results)
- Per headline: FinBERT sentiment; zero-shot topic labels (Hormuz/tanker disruption, Red Sea/Suez, iron ore
  supply, China steel demand, port congestion, oil/bunker price, sanctions/war risk).
- Daily features: count and mean sentiment per topic, 5-day change.
- Use as extra columns in the residual model, or in a LightGBM re-fit on the event window.

### M3 — The DL model (main text branch): dual-branch network with attention pooling
```
headlines in W_{t-L+1..t} ─► frozen encoder ─► per-day attention pooling ─► temporal pooling (GRU or attention over L=10 days) ─┐
                                                                                                                                  ├─► fusion MLP ─► r̂ (Huber) or q10/q50/q90 (pinball)
ML branch: [ŷ_ML, q10_ML, q90_ML, 5–10 key features] ─► small MLP ────────────────────────────────────────────────────────────┘
final: ŷ = ŷ_ML + r̂
```
- Trainable parts are small (attention + MLP, ~10–50k parameters); the encoder stays frozen. With ~250
  training days, fine-tuning a whole transformer would overfit.
- Optional variant: unfreeze the last encoder layer with **multi-instance learning**: every headline inherits
  its day's residual as a weak label, predictions are averaged per day. This gives many more training samples.
- Regularisation: dropout 0.2–0.3, weight decay, early stopping on the validation split, ensemble of 5 seeds.
- Loss: Huber on r for the point forecast; pinball at 0.1/0.5/0.9 for intervals (recalibrated with
  split-conformal on the validation split).

### Fusion alternatives (compare, report the best on validation only)
| Fusion | Formula | When |
|---|---|---|
| Residual (default) | ŷ = ŷ_ML + g(text) | Keeps the ML forecast as the base. |
| Stacking | ŷ = a·ŷ_ML + b·s_text + c (ridge) | Very few samples; transparent. |
| Gated | ŷ = ŷ_ML + σ(w·z)·g(text), z = text volume/novelty | Text should matter only on news-heavy days. |

### LLM caveat (leakage)
An LLM whose training data extend past T0 may "know" what happened after the closure. If an LLM scores
headlines, use it only for per-headline classification with **no dates in the prompt**, prefer encoders whose
pretraining ended before the window, and run the placebo tests below. Write the model and version in the
report.

## 4. Evaluation (same metrics as the ML part, same test days)
- Compare **ML only** vs **ML + M1** vs **ML + M2** vs **ML + M3** at h = 5 and h = 20: MAE, RMSE, direction
  hit rate, pinball loss, 80% coverage; Diebold–Mariano with HAC (h−1 lags). With h = 20 the test window has
  only ~4–5 independent observations per month, so add a block bootstrap and avoid strong claims.
- Sub-periods: before T0, first 4 weeks after T0, later.
- **Placebo tests:** (a) shuffle the text across days; (b) shift text by +5 trading days (stale news);
  (c) random headlines from an unrelated period. A real effect must disappear in (a) and (c).
- **Interpretation:** top-attention headlines on the largest-error days; topic contributions (M2).

## 5. Deliverables and files
| File | Producer | Columns |
|---|---|---|
| `data/text/headlines.parquet` | text | see §2 |
| `data/processed/text_daily_features.parquet` | text | `date, n_headlines, pca_1..16, topic_*, sent_*` |
| `data/processed/ml_oos_predictions.parquet` | ML | `date, h, y_true, yhat, q10, q50, q90, model_version, train_end` |
| `data/processed/text_predictions.parquet` | text | `date, h, method, r_hat, yhat_final, q10, q50, q90` |
| `experiments/results.csv` | both | one row per run |

## 6. Timeline (runs in parallel with ML weeks 3–5)
| Week | Task |
|---|---|
| ML wk 1–2 | Fix T0 and the contract; collect and clean headlines; volume plot |
| ML wk 3 | M1 and M2 on a provisional ML (ridge) residual to test the pipeline |
| ML wk 4–5 | M3 (dual-branch); placebo tests |
| after G4 | Re-run everything on the frozen `ml-v1.0` OOS predictions; final tables |

## 7. Open decisions for the team
1. T0 (exact date and source) and whether the window is 6+6 months or asymmetric.
2. Text sources actually licensed (GDELT only, or a paid outlet too).
3. Primary metric for the final slide (proposal: MAE and direction hit rate at h = 5 vs ML only, with DM p-value).
4. Whether C3/C5 are also targets in the text branch (more samples, same contract).
