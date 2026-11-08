"""Polite web requests: a pause between requests to the same site, an identifying user-agent,
retries on temporary errors, an on-disk cache (crashed runs resume) and a request log."""
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from . import config

RETRY_STATUSES = {429, 500, 502, 503, 504}


def get_logger(name: str = "news") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    to_file = logging.FileHandler(config.LOG_DIR / "news_requests.log", encoding="utf-8")
    to_file.setFormatter(fmt)
    logger.addHandler(to_file)
    return logger


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    headers: dict
    from_cache: bool

    def json(self):
        return json.loads(self.text)

    def header(self, name: str, default=None):
        """Case-insensitive header lookup."""
        lower = {k.lower(): v for k, v in self.headers.items()}
        return lower.get(name.lower(), default)


class PoliteFetcher:
    def __init__(self, delay: float = config.REQUEST_DELAY_SECONDS, max_retries: int = config.MAX_RETRIES,
                 cache_dir: Path = config.CACHE_DIR, user_agent: str = config.USER_AGENT, timeout: int = 30):
        import requests  # imported here so the rest of the package works without it

        self.delay, self.max_retries, self.timeout = delay, max_retries, timeout
        self.cache_dir = Path(cache_dir)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.9"})
        self._exceptions = requests.RequestException
        self._last_request = {}
        self.log = get_logger()

    def _cache_path(self, full_url: str) -> Path:
        key = hashlib.sha1(full_url.encode("utf-8")).hexdigest()
        return self.cache_dir / key[:2] / f"{key}.json"

    def _wait_turn(self, domain: str) -> None:
        elapsed = time.monotonic() - self._last_request.get(domain, 0.0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request[domain] = time.monotonic()

    def get(self, url: str, params: dict | None = None, use_cache: bool = True) -> FetchResult:
        full_url = f"{url}?{urlencode(sorted(params.items()))}" if params else url
        cache_file = self._cache_path(full_url)
        if use_cache and cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return FetchResult(full_url, data["status"], data["text"], data["headers"], True)

        domain = urlsplit(url).netloc
        for attempt in range(1, self.max_retries + 1):
            self._wait_turn(domain)
            try:
                resp = self.session.get(full_url, timeout=self.timeout)
            except self._exceptions as exc:
                self.log.warning("attempt %d/%d failed for %s: %s", attempt, self.max_retries, full_url, exc)
                time.sleep(self.delay * 2 ** attempt)
                continue
            self.log.info("GET %s -> %d", full_url, resp.status_code)
            if resp.status_code in RETRY_STATUSES and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After", "")
                wait = int(retry_after) if retry_after.isdigit() else self.delay * 2 ** attempt
                self.log.warning("status %d, waiting %ss before retry", resp.status_code, wait)
                time.sleep(wait)
                continue
            result = FetchResult(full_url, resp.status_code, resp.text, dict(resp.headers), False)
            if resp.status_code == 200 and use_cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps({"status": 200, "text": resp.text, "headers": dict(resp.headers)}),
                                      encoding="utf-8")
            return result
        self.log.error("giving up on %s after %d attempts", full_url, self.max_retries)
        return FetchResult(full_url, 0, "", {}, False)
