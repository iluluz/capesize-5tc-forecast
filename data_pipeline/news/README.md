# data_pipeline/news — news headlines for the text branch

Builds the text inputs of the deep-learning branch (`docs/03` §2): every relevant shipping and commodity
headline from 2025-08-01 to 2026-11-07, assigned to the Baltic trading day on which it can first be used.
Owner: Ninon. Article text is licensed and never committed; this folder holds code only.

## Sources

| Source | Content | Collection | Collected | Kept after cleaning |
| --- | --- | --- | --- | --- |
| Reuters via Factiva (MIT licence) | headline + first paragraph, exact timestamps | export by Christella | 2,298 | 1,997 |
| Hellenic Shipping News | dry bulk market reports, broker commentary, republished wires | WordPress REST API | 26,195 | 6,129 |
| gCaptain | maritime security, Hormuz coverage | WordPress REST API | 4,038 | 1,386 |
| GDELT | global news, titles + URLs | to be added | — | — |

Terms checked 2026-11-07. Hellenic Shipping News has no terms of use; its Disclaimer forbids republication
without written permission, so no text leaves the shared drive; its robots.txt `Crawl-Delay: 30` is respected.
gCaptain has no terms of use and its `llms.txt` states that full text is available to crawlers. Splash247 was
not collected (no terms found). Reuters/Factiva content is not redistributable.

## Pipeline

1. **Collect** (`scrape_wordpress.py`): all posts in the date range; title + excerpt stored as `title` + `lead`.
   Polite access: robots.txt crawl delay (minimum 3 s), identifying user-agent, on-disk cache so a crashed run resumes.
2. **Merge** (`merge.py`): every source is converted to the `docs/03` schema
   (`id, published_utc, first_seen_utc, source, outlet, url, title, lead, lang, query, retrieved_utc, date_only`).
3. **Assign news days** with the shared contract (`capesize.calendar`): window
   W_t = (12:00 UTC previous trading day, 12:00 UTC day t]; date-only items at 23:59:59 UTC; weekend and
   holiday news rolls forward.
4. **Filter** (`filters.py`): keep an item if it mentions a core term (Capesize, dry bulk, iron ore, coking or
   thermal coal, Hormuz, freight rates…) or a context term (Vale, China steel, Red Sea, tanker, war risk…)
   together with a shipping or commodity word.
5. **Deduplicate**: same URL; Reuters "UPDATE n-" versions; identical titles within 3 days; near-identical
   titles on the same day (ratio ≥ 0.95). Optional `--embed-dedup`: cosine > 0.92 on MiniLM embeddings.
6. **Volume check** (`volume_plot.py`): headlines per trading day by source.

## Results (Baltic 5TC trading days, 2025-08-01 → 2026-10-23)

9,512 relevant headlines over 309 trading days: 30.8 per day on average, no day below 5.
Monthly volume is stable at about 370 until December 2025, rises in January and February, triples in March
(1,164) after the closure on 2026-02-28, and stays near 900 until July. All three sources move together.

## Reproduce

```bash
pip install -r requirements.txt && pip install -e .
python -m data_pipeline.news.check_sources                      # robots.txt, API, sitemap per site
python -m data_pipeline.news.scrape_wordpress --source hellenic  # ~2 h 15 (30 s crawl delay)
python -m data_pipeline.news.scrape_wordpress --source gcaptain  # ~3 min
python -m data_pipeline.news.merge --factiva <factiva_articles_clean.csv> --scraped hellenic gcaptain \
       [--gdelt <gdelt.csv>] [--trading-days <5tc_dates.csv>] [--embed-dedup]
python -m data_pipeline.news.volume_plot
pytest tests/test_news_*.py
```

Outputs, under `CAPESIZE_LOCAL_DIR` (default `data/`, gitignored): `raw/news/<source>/<YYYY-MM>.jsonl`,
`text/headlines.parquet` (all collected), `text/headlines_clean.parquet` (filtered, deduplicated, with
`news_day` and topic tags), `text/headlines_per_day.parquet`, `figures/news_volume.png`.

## Known limitations

-  **News after 2026-10-23 is not used**: the 5TC series ends there, so later items have no trading day; re-run the merge with an updated date file when the ML team extends workbook 1.
- **Relevance is about 80%** on a spot check; broad terms (tanker, bunker, newbuilding) let in some general
  shipping news. The classifier's "Not relevant" label handles the rest.
- **Cross-source duplicates may be undercounted**: Hellenic republishes wire stories with reworded titles; run `--embed-dedup`.
- **27% of Reuters items have no usable lead** (editorial notes, datelines), relevant for the headline vs.
  headline + lead comparison.
- **Headline volume rises with the crisis**, so daily features should rely on averages and shares rather than raw counts.
