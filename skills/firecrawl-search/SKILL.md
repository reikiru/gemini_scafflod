---
name: firecrawl-search
description: Search the web and discover structured data providers via Firecrawl CLI through the local file bridge. Use when the user asks for web research, current news, developer docs, or structured records and wants Firecrawl search results with optional full-page scraping.
---
# firecrawl-search

Search the web and Alexandria tool catalogue using the local `firecrawl` CLI executed outside the sandbox via the file bridge.

## Bridge Execution

Invoke `firecrawl` through `bridge/gx` (with `firecrawl` allowlisted in `bridge/allowlist.conf` and `FIRECRAWL_API_KEY` configured in host-side `bridge/env.conf`). Never read or print the raw API key inside the sandbox.

## Quick Start

```bash
# Basic web search saved to JSON
gx firecrawl search "your query" -o .firecrawl/result.json --json

# Search and scrape full page content from results
gx firecrawl search "your query" --scrape -o .firecrawl/scraped.json --json

# Recent news (past day)
gx firecrawl search "your query" --sources news --tbs qdr:d -o .firecrawl/news.json --json

# Developer docs and GitHub repos
gx firecrawl search "your query" --categories developer -o .firecrawl/dev.json --json
```

## Steps

1. Run `gx firecrawl search` with `-o .firecrawl/<slug>.json --json` so large responses stay on disk instead of flooding context.
2. Inspect the saved JSON file using local file tools or `jq` to extract titles, URLs, and highlights.
3. For a specific URL that needs full markdown or structured JSON extraction, hand off to `firecrawl-scrape`.

## Gotchas

- Use `--timeout 180` on `gx` if combining `--scrape` across many results.
- Always check exit code and error fields before citing results.
