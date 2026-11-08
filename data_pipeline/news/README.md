# data_pipeline/news — news collection for the text branch

Builds the text inputs described in `docs/03` §2. Uses the shared contract: news windows come from
`capesize.calendar.assign_news_day` (12:00 UTC cutoff, date-only items at 23:59:59 UTC).

| Command (from the repo root) | What it does |
| --- | --- |
| `python -m data_pipeline.news.check_sources` | robots.txt, WordPress API and sitemap check per site |
| `python -m data_pipeline.news.scrape_wordpress --source hellenic` | collect a site (default range: 2025-08-01 → today) |
| `python -m data_pipeline.news.merge --factiva <csv> --gdelt <csv> --scraped hellenic` | merge, clean, volume check |

Outputs (all under `CAPESIZE_LOCAL_DIR`, default `data/`, gitignored):
`raw/news/<source>/<YYYY-MM>.jsonl` · `text/headlines.parquet` (everything collected) ·
`text/headlines_clean.parquet` (in a news window, relevant, deduplicated, with `news_day` and topic tags) ·
`text/headlines_per_day.parquet` (volume check).

Notes
- Trading-day grid: provisional London business days until the 5TC dates are passed with `--trading-days`.
- Scraping is polite: 3 s between requests per site, identifying user-agent (`CONTACT_EMAIL` in `.env`),
  cache in `data/cache/news/` so a crashed run resumes. Robots.txt and terms are checked before each site.
- No article text goes to Git: this repo is public and Reuters/Factiva content is licensed.
