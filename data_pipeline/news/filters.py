"""Keyword relevance rule: keep an item if it matches a core term, or a context term together with a
shipping/commodity term. Excluded topics are dropped unless a core term also appears.
Terms cover the docs/03 §2 query list plus Capesize-specific vocabulary."""
import re

CORE = [
    "capesize", "dry bulk", "drybulk", "bulk carrier", "bulk carriers", "bulker", "bulkers",
    "baltic dry index", "bdi", "baltic capesize index", "bci", "5tc", "iron ore", "coking coal",
    "thermal coal", "hormuz", "freight rates",
]
CONTEXT = [
    "china steel", "steel output", "port congestion", "port hedland", "tubarão", "tubarao", "qingdao",
    "vale", "bhp", "rio tinto", "fortescue", "simandou", "bauxite", "guinea", "bunker", "bunkers",
    "vlsfo", "fuel prices", "red sea", "suez", "cape of good hope", "rerouting", "iran", "persian gulf",
    "tanker", "tankers", "war risk", "sanctions", "tonne-miles", "tonne miles", "fleet", "newbuilding",
    "newbuildings", "scrapping",
]
SHIPPING_OR_COMMODITY = [
    "shipping", "ship", "ships", "vessel", "vessels", "freight", "cargo", "cargoes", "port", "ports",
    "bulk", "charter", "chartering", "tonnage", "maritime", "seaborne", "shipowner", "shipowners",
    "iron ore", "coal", "steel", "commodity", "commodities", "exports", "imports", "mining", "strait",
    "insurance", "transit", "transits",
]
EXCLUDE = [
    "container line", "container lines", "cruise", "yacht", "yachts", "ferry", "ferries",
    "crew recruitment", "award", "awards", "conference", "webinar", "sponsored",
]


def _compile(terms):
    return {t: re.compile(rf"(?<!\w){re.escape(t)}(?!\w)", re.IGNORECASE) for t in terms}


_CORE, _CONTEXT, _ANCHOR, _EXCLUDE = map(_compile, (CORE, CONTEXT, SHIPPING_OR_COMMODITY, EXCLUDE))


def _found(patterns, text):
    return [t for t, p in patterns.items() if p.search(text)]


def is_relevant(title: str, lead: str | None = None) -> tuple[bool, list[str]]:
    """Returns (keep, matched core and context terms)."""
    text = f"{title} {lead or ''}"
    core, context = _found(_CORE, text), _found(_CONTEXT, text)
    matched = sorted(set(core + context))
    if core:
        return True, matched
    if _found(_EXCLUDE, text):
        return False, matched
    if context and _found(_ANCHOR, text):
        return True, matched
    return False, matched
