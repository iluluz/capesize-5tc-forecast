import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.news.merge import build, clean_reuters_lead, normalize_title  # noqa: E402
from data_pipeline.news.schema import HEADLINE_COLUMNS  # noqa: E402
from data_pipeline.news.trading_days import provisional_trading_days  # noqa: E402


def rows(items):
    """items: (first_seen_utc, title, date_only)"""
    return pd.DataFrame([{
        "id": f"t{i}", "published_utc": ts, "first_seen_utc": ts, "source": "reuters_factiva",
        "outlet": "Reuters News", "url": None, "title": title, "lead": None, "lang": "en",
        "query": "test", "retrieved_utc": None, "date_only": d,
    } for i, (ts, title, d) in enumerate(items)])[HEADLINE_COLUMNS]


def test_reuters_lead_cleaning():
    assert clean_reuters_lead("(Updates prices on market close)") is None
    assert clean_reuters_lead("Aug 1 (Reuters) - Vale SA:") is None
    lead = "BEIJING, Aug 1 (Reuters) - Iron ore futures were little changed on Friday but set for a weekly loss."
    assert clean_reuters_lead(lead).startswith("Iron ore futures")


def test_update_prefixes_are_ignored():
    assert normalize_title("UPDATE 2-Iron ore heads for weekly loss") == "iron ore heads for weekly loss"


def test_news_days_follow_the_contract_and_duplicates_go():
    grid = provisional_trading_days(date(2026, 2, 2), date(2026, 4, 30))
    df = rows([
        ("2026-02-28T10:00:00Z", "Iran closes the Strait of Hormuz to shipping", False),        # Saturday
        ("2026-02-28T11:00:00Z", "UPDATE 1-Iran closes the Strait of Hormuz to shipping", False),  # copy
        ("2026-03-06T00:00:00Z", "Capesize rates firm on iron ore demand", True),                 # date only, Fri
        ("2026-04-02T15:00:00Z", "Iron ore slips before Easter break", False),                    # Thu afternoon
        ("2026-03-04T09:00:00Z", "Cruise line adds new routes", False),                           # irrelevant
    ])
    _, clean, per_day, report = build([df], grid)
    days = dict(zip(clean["title"], clean["news_day"].dt.date, strict=True))
    assert days["Iran closes the Strait of Hormuz to shipping"] == date(2026, 3, 2)   # weekend rolls to Monday
    assert days["Capesize rates firm on iron ore demand"] == date(2026, 3, 9)          # 23:59:59 -> next window
    assert days["Iron ore slips before Easter break"] == date(2026, 4, 7)              # Good Friday + Easter Monday
    assert len(clean) == 3                                                             # UPDATE copy and cruise gone
    assert report["volume"]["days_with_zero"] > 0
