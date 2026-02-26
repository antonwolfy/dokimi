# Using Multiple Documentation Sources

By default `doc-benchmark` fetches docs from [Context7](https://context7.com/).
With `--doc-source` you can point it at a local directory or any URL instead.

## Quick reference

| Flag value | What it does |
|---|---|
| `context7` | Context7 cloud API (default) |
| `local:<path>` | Local `.md` / `.rst` / `.html` / `.txt` files |
| `url:<url>` | Fetch and search a single web page |

---

## Examples

```bash
# Default — Context7
python cli.py answers generate --product oneTBB --questions questions/oneTBB.json

# Local Sphinx HTML build
python cli.py answers generate --product oneTBB --questions questions/oneTBB.json \
  --doc-source local:/path/to/oneTBB/docs/_build/html

# Remote API reference page
python cli.py answers generate --product oneTBB --questions questions/oneTBB.json \
  --doc-source url:https://spec.oneapi.io/versions/latest/elements/oneTBB/source/nested-index.html

# Full pipeline with local docs
python cli.py evaluate --product oneTBB --repo uxlfoundation/oneTBB \
  --doc-source local:/path/to/docs
```

`--doc-source` is supported by `answers generate`, `questions generate`, and `evaluate`.

---

## Adding a custom source

Implement the three-method `MCPClient` interface and register it in the factory.

### 1 — Create the client

```python
# doc_benchmarks/mcp/confluence.py
import re
from typing import List, Dict, Any, Optional
import httpx
from . import MCPClient, MCPConnectionError

class ConfluenceClient(MCPClient):
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def resolve_library_id(self, library_name: str) -> str:
        return f"confluence:{library_name}"

    def get_library_docs(
        self,
        library_id: str,
        query: str,
        max_results: int = 5,
        max_tokens: int = 8000,
    ) -> List[Dict[str, Any]]:
        """Search Confluence and return relevant page excerpts."""
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = httpx.get(
            f"{self.base_url}/rest/api/content/search",
            params={"cql": f'text ~ "{query}"', "limit": max_results},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        pages = resp.json().get("results", [])
        return [
            {
                "content": p["body"]["storage"]["value"][:max_tokens * 4],
                "source": "confluence",
                "url": f"{self.base_url}/wiki{p['_links']['webui']}",
                "library_id": library_id,
                "query": query,
                "relevance_score": 1.0,
            }
            for p in pages
        ]

    def check_connection(self) -> bool:
        try:
            r = httpx.head(self.base_url, timeout=10)
            return r.status_code < 400
        except Exception:
            return False
```

### 2 — Register in the factory

```python
# doc_benchmarks/mcp/factory.py  (add inside create_doc_source_client)

    if doc_source.startswith("confluence:"):
        from .confluence import ConfluenceClient
        import os
        url, _, space = doc_source[len("confluence:"):].partition("/")
        return ConfluenceClient(
            base_url=url,
            token=os.environ["CONFLUENCE_TOKEN"],
        )
```

### 3 — Use it

```bash
CONFLUENCE_TOKEN=xxx python cli.py answers generate \
  --product myLib \
  --questions questions/myLib.json \
  --doc-source confluence:https://wiki.example.com
```

---

## How relevance scoring works

`LocalMarkdownClient` and `URLClient` use a lightweight keyword-overlap score:

```
score = (query tokens found in chunk) / (total query tokens)
```

Chunks are ranked by this score and the top `max_results` are returned.
The Context7 client delegates ranking to the Context7 API (topic-based retrieval).
