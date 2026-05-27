# Browser Access Strategies for Gossip Engine

Three approaches to give agents the ability to search and browse the web, ordered from simplest to most capable.

---

## Strategy 1: Browser Builtins in the Sandbox

Add `browse(url)` and `search(query)` as injected globals in the subprocess. The sandbox already restricts execution via `SAFE_BUILTINS` — these are just two more safe functions.

### Implementation

```python
# gossip_engine/grounding/browser.py
import httpx
import time
from urllib.parse import urlparse

_client = httpx.Client(timeout=15.0, follow_redirects=True)
_last_call = 0.0
_RATE_LIMIT = 1.0  # seconds between calls
_ALLOWED_DOMAINS = None  # None = any domain, or set(["example.com"])


def browse(url: str) -> str:
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < _RATE_LIMIT:
        time.sleep(_RATE_LIMIT - elapsed)
    _last_call = time.time()
    parsed = urlparse(url)
    if _ALLOWED_DOMAINS and parsed.netloc not in _ALLOWED_DOMAINS:
        return "Error: domain not allowed"
    try:
        resp = _client.get(url, headers={"User-Agent": "GossipEngine/1.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            text = resp.text[:50000]
        else:
            text = resp.text[:10000]
        return text
    except Exception as e:
        return f"Error: {e}"


def search(query: str, num: int = 5) -> str:
    results = []
    # DuckDuckGo-style search (no API key needed)
    url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
    html = browse(url)
    # Basic extraction of result links
    for line in html.split("\n"):
        if 'class="result__a"' in line:
            results.append(line.strip()[:200])
    return "\n".join(results[:num]) if results else f"Searched: {query}"
```

```python
# gossip_engine/grounding/sandbox.py
from .browser import browse, search

SAFE_BROWSER = {
    "browse": browse,
    "search": search,
}
SAFE_BUILTINS.update(SAFE_BROWSER)
```

Agent genome can then call them directly:

```python
def solve(query):
    results = search(query)
    page = browse(results[0]["url"])
    return "answer found" in page
```

### Pros
- ~50 lines of code, minimal change
- Agents use naturally (Python function calls)
- Rate limits + timeouts built in
- `env={}` subprocess keeps environment isolation

### Cons
- Agents now have network access (mitigated by allowlist + timeouts)
- No caching between agents (each call hits network)
- Single-process httpx client (not async)

---

## Strategy 2: Gossip Tool Server (MCP-like)

Run a separate background process that exposes browse/search via a local socket. The orchestrator queues requests and returns results asynchronously.

### Architecture

```
┌─────────────────┐     localhost:9876     ┌──────────────────┐
│  Agent Genome   │                        │  Tool Server     │
│  calls browse() │──── request ──────────▶│  - httpx client  │
│                 │◀──── response ────────│  - headless Cr.  │
│  result in      │                        │  - rate limiter  │
│  execution env  │                        │  - cache layer   │
└─────────────────┘                        └──────────────────┘
```

### Protocol

```python
# gossip_engine/tools/protocol.py
@dataclass
class ToolRequest:
    id: str
    tool: str        # "browse" | "search" | "screenshot"
    args: dict

@dataclass
class ToolResponse:
    id: str
    result: str
    error: str | None
```

### Implementation Sketch

**Server** (background process):
```python
# gossip_engine/tools/server.py
import httpx, asyncio, json
from playwright.async_api import async_playwright  # for screenshots

async def handle_request(data: dict) -> dict:
    tool = data["tool"]
    if tool == "browse":
        async with httpx.AsyncClient() as c:
            r = await c.get(data["url"], timeout=15)
            return {"text": r.text[:100000]}
    elif tool == "screenshot":
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(data["url"])
            screenshot = await page.screenshot(full_page=True)
            return {"screenshot_b64": base64.b64encode(screenshot).decode()}
```

**Orchestrator integration**:
```python
# In orchestrator.py, agents don't call network directly.
# Instead, genome is transformed: browse(x) → _TOOLS.browse(x)
# The tools proxy queues requests to the server process.
```

### Pros
- Full isolation (sandbox has zero network)
- Rate limiting, caching, logging all in one place
- Can support screenshots, JavaScript rendering, PDF generation
- Tools can be hot-swapped without changing agent code
- Fits the gossip protocol model (Phase 2)

### Cons
- ~200+ lines of code
- Needs async coordination (or polling)
- Agents block waiting for results
- Browser dependency (Playwright) adds ~200MB

---

## Strategy 3: Orchestrator Pre-fetch + Context Injection

The orchestrator periodically scrapes relevant pages and injects them into agent memory before evaluation. Agents never call browse themselves — they receive pre-fetched data through the memory architecture.

### Architecture

```
Round N:
  1. Orchestrator checks L4 codebook for stale/stale entries
  2. Orchestrator performs search/browse on relevant topics
  3. Results stored in L4 codebook (shared agent knowledge)
  4. Agents read from codebook during evaluation
  5. High-trust results promoted to L5 global workspace
```

### Implementation

```python
# gossip_engine/tools/prefetch.py
class PrefetchManager:
    def __init__(self, codebook: CodebookStore):
        self.codebook = codebook

    def refresh_topics(self, topics: list[str]):
        for topic in topics:
            existing = self.codebook.search(topic)
            if existing and not self._is_stale(existing):
                continue
            results = search(topic)
            content = browse(results[0])
            self.codebook.store(
                key=topic,
                content=content,
                source="web",
                ttl=3600,
            )
```

```python
# orchestrator.py — during each round
self.prefetcher.refresh_topics(self._get_active_topics())
# Agents see pre-fetched content via L4 memory
```

### Pros
- Cleanest isolation (sandbox unchanged)
- Fits existing memory architecture (L4 codebook, L5 workspace)
- No agent code changes — they just read memory
- Fetch once, use many times (efficient)
- Can be scheduled (e.g., refresh every N rounds)

### Cons
- Agents can't browse on-demand
- Orchestrator must guess what to fetch (or agent signals what it needs)
- Stale content if pages change rapidly
- Not useful for interactive debugging of live pages

---

## Recommendation Flow

```
Starting from zero browser access:

┌─ Strategy 1 (quick MVP) ──────────────────────┐
│ 1. Implement browser.py (~50 lines)            │
│ 2. Add to SAFE_BUILTINS in sandbox             │
│ 3. Agents can browse immediately               │
└────────────────────────────────────────────────┘
                       │
                       ▼
┌─ Strategy 2 (production) ─────────────────────┐
│ 1. Implement tool server (~200 lines)          │
│ 2. Agents call through proxy in orchestator    │
│ 3. Add screenshot capability                   │
│ 4. Cache + rate limit at server level          │
└────────────────────────────────────────────────┘
                       │
                       ▼
┌─ Strategy 3 (memory-native) ──────────────────┐
│ 1. Implement prefetch manager                  │
│ 2. Wire into L4 codebook store                 │
│ 3. Agents read from memory, not network        │
│ 4. Best fit for gossip protocol Phase 2        │
└────────────────────────────────────────────────┘
```

**Quickest path**: Start with Strategy 1 (browser builtins), add Strategy 3 (prefetch) as the gossip memory layer matures, then optionally add Strategy 2 (tool server) for advanced capabilities like screenshots.
