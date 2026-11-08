"""Check how each WordPress news site can be collected: robots.txt rules, whether the REST API answers
(and how many posts fall in the collection range), and whether a sitemap exists. Sends a handful of
requests, nothing cached.

Usage:  python -m data_pipeline.news.check_sources
"""
from datetime import date

from . import config
from .fetch import PoliteFetcher
from .scrape_wordpress import SITES, crawl_delay


def robots_rules(text: str) -> list[str]:
    """Lines of the robots.txt block for all crawlers (User-agent: *)."""
    rules, in_star = [], False
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if line.lower().startswith("user-agent:"):
            in_star = line.split(":", 1)[1].strip() == "*"
        elif in_star and line:
            rules.append(line)
    return rules


def main():
    fetcher = PoliteFetcher()
    for source, base in SITES.items():
        print(f"\n=== {source}: {base}")
        robots = fetcher.get(f"{base}/robots.txt", use_cache=False)
        delay = max(config.REQUEST_DELAY_SECONDS, crawl_delay(robots.text) or 0) if robots.status == 200 \
            else config.REQUEST_DELAY_SECONDS
        if robots.status == 200:
            rules = robots_rules(robots.text)
            print("robots.txt rules for all crawlers:", *(rules or ["(none)"]), sep="\n  ")
            blocked = [r for r in rules if r.lower().startswith("disallow:") and "/wp-json" in r.lower()]
            print("  -> /wp-json/ is DISALLOWED" if blocked else "  -> /wp-json/ is not disallowed")
        else:
            print(f"robots.txt: status {robots.status}")

        api = fetcher.get(f"{base}/wp-json/wp/v2/posts", use_cache=False, params={
            "per_page": 1, "_fields": "id,date",
            "after": f"{config.COLLECTION_START}T00:00:00", "before": f"{date.today()}T23:59:59"})
        total = api.header("X-WP-Total")
        if api.status == 200 and total:
            pages = int(total) // 100 + 1
            print(f"WordPress API: OPEN, {total} posts in range ({pages} pages, {delay:.0f} s between "
                  f"requests, about {pages * delay / 60:.0f} min)")
        else:
            print(f"WordPress API: not usable (status {api.status})")

        for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml"):
            if fetcher.get(f"{base}{path}", use_cache=False).status == 200:
                print(f"Sitemap: found at {path}")
                break
        else:
            print("Sitemap: not found at the usual addresses")
    print("\nAlso read each site's terms of use by hand and record the result.")


if __name__ == "__main__":
    main()
