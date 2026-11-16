# Text branch: news sentiment for Capesize rates

**Question:** does daily shipping and commodity news, scored by a model that understands what is good or bad *for Capesize freight rates*, make the 5TC forecast more accurate, especially around the Strait of Hormuz closure (28 Feb 2026)?

**Owners:** Christella (labels, model, evaluation of the text model) · Ninon (news pipeline, daily features, with/without-news test)

## 1. Data
| Source | Headlines | Access |
|---|---|---|
| Hellenic Shipping News | 6,129 | Free, WordPress API (robots.txt and terms checked) |
| Reuters News | 1,997 | Factiva via MIT Libraries, manual export (licensed: **not in this repo**) |
| gCaptain | 1,386 | Free, WordPress API |
| **Total** | **9,512** | 1 Aug 2025 – 23 Oct 2026, ~31 headlines per trading day |

Each headline is assigned to a Baltic trading day with the shared contract (`src/capesize/calendar.py`): news counts for day *t* only if first published before **12:00 UTC** on *t* (before the Baltic publication), weekend news rolls forward. Duplicates (same URL, Reuters "UPDATE" versions, near-identical titles) keep the earliest copy. GDELT headlines (12,903, free web news) are kept as a separate comparison.

## 2. Labels
General financial sentiment often points the wrong way for freight: an attack near Hormuz is "negative" news but *bullish* for Capesize rates. So every headline gets one of four Capesize-specific labels: **bullish · neutral · bearish · not relevant** ([labelling guide](colab/labelling_guide.md)).

- **Automatic labels:** `Qwen/Qwen2.5-7B-Instruct` (released Sep 2024, so trained **before** our window: it cannot know how the 2026 crisis played out). Prompt = the labelling guide; input = headline + lead, no dates. No text generation: one forward pass, softmax over the four answer letters. Exact settings: [`llm_labelling_details.md`](colab/llm_labelling_details.md).
- **Human check:** Christella and Ninon labelled the same 100 random headlines blind (50 before, 50 after the closure), held out from training. Headlines that are also prompt examples are excluded.
- Label shares (LLM): 26% bullish, 23% neutral, 14% bearish, 37% not relevant.

## 3. Model
- **Baseline:** plain FinBERT (`ProsusAI/finbert`, general financial tone).
- **Main model:** FinBERT fine-tuned on the LLM labels, 4 classes, trained **only on headlines before 28 Mar 2026** (closure + 1 month), so everything after is out-of-sample. 3 epochs, lr 2e-5, batch 32, best epoch by validation macro-F1. Two versions: headline only / headline + lead.
- Agreement with the LLM labels on unseen headlines: 74.6% (headline) and **77.5% (headline + lead)**.
- **Daily features** (`text_daily_features.parquet`, 309 trading days): mean sentiment (P(bullish) − P(bearish)) for each model, bullish/bearish shares, per-topic sentiment (freight, Hormuz, iron ore/coal), 5- and 20-day backward-looking averages, relative news volume.

## 4. Results
**Accuracy against our hand labels** (2 annotators labelled the same 100 headlines blind: 89% agreement, Cohen's κ = 0.85; gold set = the 89 headlines where both agree):
| Model | Accuracy | Macro-F1 | Direction swaps* |
|---|---|---|---|
| Plain FinBERT, headline | 41.6% | 0.350 | 26.3% |
| Plain FinBERT, headline + lead | 32.6% | 0.277 | 36.8% |
| LLM (Qwen2.5-7B) | 65.2% | 0.658 | 13.2% |
| Fine-tuned FinBERT, headline + lead | 64.0% | 0.659 | 10.5% |
| **Fine-tuned FinBERT, headline** | **66.3%** | **0.676** | **5.3%** |

\*Share of directional headlines labelled the opposite way (bullish ↔ bearish). Plain FinBERT has no "not relevant" class. Leaving out the one headline that is also a prompt example changes the LLM to 64.8%.
The small fine-tuned model matches the 7B LLM it learned from and makes far fewer direction errors than general sentiment. Its main error is calling neutral headlines bullish (10 of 32), the bullish lean also visible in Jun–Jul 2026.

**Hormuz case study** (average daily sentiment, −1 bearish … +1 bullish):
| Model | Before closure | After closure | After 28 Mar (out-of-sample) |
|---|---|---|---|
| Fine-tuned FinBERT | +0.06 | +0.25 | **+0.23** |
| LLM labels | +0.05 | +0.22 | +0.18 |
| Plain FinBERT | +0.08 | −0.06 | −0.05 |

Before the closure all three move together; after it, the Capesize-specific models turn bullish while general tone turns negative. Chart: `figures/hormuz_case_study.png`.

**Does news improve the forecast?** A ridge model on 5 daily text features learns the error of the ML forecast (walk-forward inside the event window; same result on `ml-v1.1` and `ml-v1.0`):
- **No reliable gain beyond a bias correction.** At h = 20 the error drops 20–28% with news, but a constant alone gives −18%, and the placebo with news from an unrelated period does as well as the real news.
- **By-product for the ML team:** the ML forecast was systematically biased after the closure; a simple bias correction improves the 4-week forecast by about 18%.
- Code and detailed results: `data_pipeline/news/forecast_test.py` and `data_pipeline/news/README.md`.

**Takeaway:** the text model reads the news correctly for Capesize (and turned bullish weeks before rates rose), but in a 14-month window it does not add forecast accuracy on top of the ML model. Best use: monitoring and early warning around shocks, and a longer history before using it as a forecast input.

## 5. Limitations
- 100 hand-labelled headlines (89 in the gold set): accuracy is ±~10 percentage points.
- Fine-tuned FinBERT leans bullish (32% bullish vs 26% for the LLM; neutral → bullish is its main error).
- Reuters text is licensed: the code is here, the data is not. Re-running needs MIT Factiva access.
- One crisis, ~14 months of news (~87 test days): too short to detect a small forecasting effect; the case study is suggestive, not proof.

## 6. Reproduce
1. News: `data_pipeline/news/` (scrapers + merge) and `text_branch/factiva_clean.py` (Factiva exports) → `headlines_clean.parquet`
2. Labels: `colab/01_llm_labels.ipynb` (Colab T4, ~2h20)
3. Fine-tune + score + accuracy: `colab/02_finetune_finbert.ipynb` (Colab T4, ~15 min)
4. Scoring, daily features, hand-check evaluation, forecast test: `data_pipeline/news/` (`score_finbert.py`, `daily_features.py`, `evaluate_check.py`, `forecast_test.py`)
5. Charts: `python text_branch/plot_hormuz.py` (news only; with `--tc <5TC workbook>` it adds the licensed 5TC panel and saves `*_PRIVATE.png`, never commit those)
