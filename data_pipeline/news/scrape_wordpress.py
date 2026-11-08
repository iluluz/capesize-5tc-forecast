"""Scraper for news sites that expose the WordPress REST API (Hellenic Shipping News, gCaptain, Splash247).

Collects every post in a date range (title + excerpt as lead) and writes monthly JSON Lines files to
<CAPESIZE_LOCAL_DIR>/raw/news/<source>/<YYYY-MM>.jsonl in the headlines schema. Re-running a range is
safe: rows are merged by id, and pages already downloaded come from the cache.

Usage (from the repository root):
    python -m data_pipeline.news.scrape_wordpress --source hellenic --start 2025-09-01 --end 2025-09-02
"""
import argparse
import html
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import config
from .fetch import PoliteFetcher, get_logger
from .schema import make_row

SITES = {
    "hellenic": "https://www.hellenicshippingnews.com",
    "gcaptain": "https://gcaptain.com",
    "splash247": "https://splash247.com",
}
POST_FIELDS = "id,date,date_gmt,link,title,excerpt"
MAX_LEAD_CHARS = 600
_TAG_RE = re.compile(r"<[^>]+>")


def clean_html(fragment: str | None) -> str:
    """Strip tags and entities, drop WordPress 'read more' tails, collapse spaces."""
    text = html.unescape(_TAG_RE.sub(" ", fragment or ""))
    for tail in ("[…]", "[...]", "Continue reading", "Read more"):
        text = text.split(tail)[0]
    if " appeared first on " in text:
        text = text.split(" The post ")[0]
    return " ".join(text.split())


def iter_posts(fetcher: PoliteFetcher, base: str, start: date, end: date):
    """Yield raw posts. The API filters in site-local time, so ask one extra day on each side and
    filter on the UTC date afterwards."""
    params = {
        "after": f"{start - timedelta(days=1)}T00:00:00",
        "before": f"{end + timedelta(days=2)}T00:00:00",
        "per_page": 100, "orderby": "date", "order": "asc", "_fields": POST_FIELDS,
    }
    page, total_pages = 1, None
    while total_pages is None or page <= total_pages:
        res = fetcher.get(f"{base}/wp-json/wp/v2/posts", {**params, "page": page})
        if res.status != 200:
            raise RuntimeError(f"API returned status {res.status} for {res.url}")
        if total_pages is None:
            total_pages = int(res.header("X-WP-TotalPages", 1))
        yield from res.json()
        page += 1


def parse_post(post: dict, source: str) -> dict:
    """Convert one WordPress post into a headlines row."""
    raw_date = post.get("date_gmt") or post["date"]
    published = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
    lead = clean_html(post.get("excerpt", {}).get("rendered"))[:MAX_LEAD_CHARS] or None
    return make_row(
        source=source,
        url=post["link"],
        title=clean_html(post["title"]["rendered"]),
        lead=lead,
        published_utc=published,
        query="wp_api:all_posts",
    )


def save_rows(rows: list[dict], source: str) -> dict[str, int]:
    """Merge rows into monthly files by id. Returns rows per month file."""
    by_month = defaultdict(list)
    for row in rows:
        by_month[row["published_utc"][:7]].append(row)
    counts = {}
    for month, month_rows in sorted(by_month.items()):
        path = config.RAW_DIR / source / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                existing[r["id"]] = r
        existing.update({r["id"]: r for r in month_rows})
        ordered = sorted(existing.values(), key=lambda r: r["published_utc"])
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ordered) + "\n", encoding="utf-8")
        counts[month] = len(ordered)
    return counts


def crawl_delay(robots_text: str) -> float | None:
    """Crawl-Delay (seconds) from the robots.txt block for all crawlers (User-agent: *), if any."""
    in_star = False
    for line in robots_text.splitlines():
        line = line.split("#")[0].strip()
        if line.lower().startswith("user-agent:"):
            in_star = line.split(":", 1)[1].strip() == "*"
        elif in_star and line.lower().startswith("crawl-delay:"):
            try:
                return float(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def scrape(source: str, start: date, end: date) -> None:
    log = get_logger()
    fetcher = PoliteFetcher()
    robots = fetcher.get(f"{SITES[source]}/robots.txt", use_cache=False)
    delay = crawl_delay(robots.text) if robots.status == 200 else None
    if delay and delay > fetcher.delay:
        fetcher.delay = delay  # respect the site's requested pause between requests
    log.info("%s: waiting %.0f s between requests", source, fetcher.delay)
    rows, failed, outside = [], 0, 0
    for post in iter_posts(fetcher, SITES[source], start, end):
        try:
            row = parse_post(post, source)
        except Exception as exc:  # keep going, but count and log every failure
            failed += 1
            log.warning("could not parse post %s: %s", post.get("link"), exc)
            continue
        if start <= date.fromisoformat(row["published_utc"][:10]) <= end:
            rows.append(row)
        else:
            outside += 1
    counts = save_rows(rows, source)
    log.info("RUN SUMMARY source=%s dates=%s..%s collected=%d failed=%d outside_range=%d files=%s",
             source, start, end, len(rows), failed, outside, counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, choices=sorted(SITES))
    parser.add_argument("--start", type=date.fromisoformat, default=config.COLLECTION_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    scrape(args.source, args.start, args.end)


if __name__ == "__main__":
    main()
