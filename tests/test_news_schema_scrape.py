import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.news.schema import canonical_url, make_row  # noqa: E402
from data_pipeline.news.scrape_wordpress import parse_post  # noqa: E402


def test_canonical_url_strips_tracking():
    assert canonical_url("HTTPS://GCaptain.com/story/?utm_source=x#c") == "https://gcaptain.com/story/"


def test_invalid_row_is_refused():
    with pytest.raises(ValueError):
        make_row(source="unknown_site", title="T", published_utc="2026-03-02T09:15:00Z")


def test_parse_wordpress_post():
    post = {
        "id": 1, "date": "2026-03-02T11:15:00", "date_gmt": "2026-03-02T09:15:00",
        "link": "https://www.hellenicshippingnews.com/capesize-jump/?utm_source=rss",
        "title": {"rendered": "Capesize rates jump as Hormuz closure reroutes &#8216;tonnage&#8217;"},
        "excerpt": {"rendered": "<p>Rates for the largest bulkers rose 12% overnight [&hellip;]</p>"},
    }
    row = parse_post(post, "hellenic")
    assert row["published_utc"] == row["first_seen_utc"] == "2026-03-02T09:15:00Z"
    assert row["title"] == "Capesize rates jump as Hormuz closure reroutes \u2018tonnage\u2019"
    assert row["lead"] == "Rates for the largest bulkers rose 12% overnight"
    assert row["url"] == "https://www.hellenicshippingnews.com/capesize-jump/"
    assert row["id"].startswith("hellenic_") and row["date_only"] is False


def test_crawl_delay_is_read_from_robots():
    from data_pipeline.news.scrape_wordpress import crawl_delay

    assert crawl_delay("User-agent: *\nCrawl-Delay: 30\n") == 30.0
    assert crawl_delay("User-agent: Googlebot\nCrawl-delay: 5\nUser-agent: *\nDisallow: /wp-admin/\n") is None
