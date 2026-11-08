import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for data_pipeline

from data_pipeline.news.filters import is_relevant  # noqa: E402


def keep(title, lead=None):
    return is_relevant(title, lead)[0]


def test_core_terms_keep():
    assert keep("Capesize rates surge on Brazilian iron ore demand")
    assert keep("Iran shuts the Strait of Hormuz to all shipping")


def test_context_needs_a_shipping_or_commodity_term():
    assert keep("Red Sea disruption lifts freight costs")
    assert keep("War risk insurance for tankers doubles in the Gulf")
    assert not keep("Iran holds talks with European ministers")
    assert not keep("Vale shares rise after earnings beat")


def test_excluded_topics_drop_unless_core():
    assert not keep("Cruise line reports record bookings at Suez port")
    assert keep("Bulk carrier collides with cruise ship near Qingdao")


def test_whole_words_only():
    assert not keep("Valeo expands car parts plant")
