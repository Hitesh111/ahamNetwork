from __future__ import annotations
import re
import time
import json
import logging
from urllib.request import Request, urlopen
from urllib.parse import urlparse, quote
from html.parser import HTMLParser

logger = logging.getLogger("gossip_engine.grounding.browser")

_RATE_LIMIT = 1.0
_last_call = 0.0
_MAX_TEXT = 50000
_BLOCKED_DOMAINS: set[str] | None = None
_TIMEOUT = 15


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    @property
    def text(self) -> str:
        return " ".join(self._text)


def _rate_limit():
    global _last_call
    now = time.time()
    elapsed = now - _last_call
    if elapsed < _RATE_LIMIT:
        time.sleep(_RATE_LIMIT - elapsed)
    _last_call = time.time()


def browse(url: str, limit: int = _MAX_TEXT) -> dict:
    """Fetch a URL and return its visible text content.

    Returns dict with keys: url, status, content, error.
    """
    _rate_limit()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"url": url, "status": 0, "content": "", "error": "Only http/https supported"}
    if _BLOCKED_DOMAINS and parsed.netloc in _BLOCKED_DOMAINS:
        return {"url": url, "status": 0, "content": "", "error": "Domain blocked"}
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; GossipEngine/1.0)"})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read(limit + 10000)
            content_type = resp.headers.get("Content-Type", "")
            final_url = resp.url
        if "application/json" in content_type:
            try:
                content = json.dumps(json.loads(raw), indent=2)
            except json.JSONDecodeError:
                content = raw.decode("utf-8", errors="replace")
        else:
            decoder = _TextExtractor()
            decoder.feed(raw.decode("utf-8", errors="replace"))
            content = decoder.text[:limit]
        return {"url": final_url, "status": 200, "content": content, "error": None}
    except Exception as e:
        return {"url": url, "status": 0, "content": "", "error": str(e)}


def search(query: str, num: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo's HTML interface.

    Returns list of dicts with keys: title, url, snippet.
    """
    _rate_limit()
    encoded = quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; GossipEngine/1.0)"})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            html = resp.read(50000).decode("utf-8", errors="replace")
    except Exception as e:
        return [{"title": f"Search error: {e}", "url": "", "snippet": ""}]

    results: list[dict] = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    ):
        href = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= num:
            break

    return results if results else [{"title": f"No results for: {query}", "url": "", "snippet": ""}]
