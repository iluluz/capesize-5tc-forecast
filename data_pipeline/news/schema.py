"""Row format of data/text/headlines.parquet (docs/03 §2), shared by every news source.

Columns from docs/03: id, published_utc, first_seen_utc, source, url, title, lead, lang, query, retrieved_utc.
Added: date_only (the item had a date but no time; needed by capesize.calendar.to_utc) and outlet
(publisher name when a source aggregates several outlets, e.g. GDELT domains).
"""
import hashlib
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HEADLINE_COLUMNS = ["id", "published_utc", "first_seen_utc", "source", "outlet", "url", "title", "lead",
                    "lang", "query", "retrieved_utc", "date_only"]
SOURCES = {"reuters_factiva", "gdelt", "hellenic", "gcaptain", "splash247", "miningcom"}
_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def canonical_url(url: str) -> str:
    """Lower-case scheme and host, drop tracking parameters and fragments."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING_PREFIXES)]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def make_id(source: str, key: str) -> str:
    """Stable id: source prefix + first 12 hex characters of the SHA-1 of the key (URL or source id)."""
    return f"{source}_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_TS_FORMAT)


def validate_row(row: dict) -> list[str]:
    """Return a list of problems; empty means valid."""
    errors = []
    missing = [c for c in HEADLINE_COLUMNS if c not in row]
    if missing:
        errors.append(f"missing columns: {missing}")
    if row.get("source") not in SOURCES:
        errors.append(f"unknown source: {row.get('source')!r}")
    if not row.get("title"):
        errors.append("empty title")
    for col in ("published_utc", "first_seen_utc"):
        try:
            datetime.strptime(row.get(col) or "", _TS_FORMAT)
        except ValueError:
            errors.append(f"{col} not in YYYY-MM-DDTHH:MM:SSZ format: {row.get(col)!r}")
    if not isinstance(row.get("date_only"), bool):
        errors.append("date_only must be true or false")
    return errors


def make_row(*, source, title, published_utc, url=None, source_key=None, first_seen_utc=None, lead=None,
             outlet=None, lang="en", query=None, date_only=False) -> dict:
    """Build a validated row. Timestamps may be datetimes or ISO strings; first_seen defaults to published."""
    if isinstance(published_utc, datetime):
        published_utc = utc_iso(published_utc)
    if isinstance(first_seen_utc, datetime):
        first_seen_utc = utc_iso(first_seen_utc)
    url = canonical_url(url) if url else None
    row = {
        "id": make_id(source, source_key or url or f"{published_utc}|{title}"),
        "published_utc": published_utc,
        "first_seen_utc": first_seen_utc or published_utc,
        "source": source,
        "outlet": outlet or source,
        "url": url,
        "title": " ".join(title.split()),
        "lead": " ".join(lead.split()) if lead else None,
        "lang": lang,
        "query": query,
        "retrieved_utc": utc_iso(datetime.now(timezone.utc)),
        "date_only": date_only,
    }
    errors = validate_row(row)
    if errors:
        raise ValueError(f"Invalid row ({url or title}): {errors}")
    return row
