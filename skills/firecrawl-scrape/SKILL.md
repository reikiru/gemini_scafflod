---
name: firecrawl-scrape
description: Scrape a known webpage, JS-rendered SPA, or PDF into clean Markdown or structured JSON via Firecrawl CLI through the local file bridge. Use when the user provides a URL or wants full page content, main article text, or schema-based JSON extraction.
---
# firecrawl-scrape

Extract clean Markdown, links, or schema-validated JSON from known URLs and PDFs using `firecrawl scrape` over the local file bridge.

## Bridge Execution

Invoke `firecrawl` through `bridge/gx` (with `firecrawl` in `bridge/allowlist.conf` and `FIRECRAWL_API_KEY` in host-side `bridge/env.conf`).

## Quick Start

```bash
# Clean main-content markdown
gx firecrawl scrape "<url>" --only-main-content -o .firecrawl/page.md

# Wait for JS-rendered SPA content
gx firecrawl scrape "<url>" --wait-for 3000 -o .firecrawl/page.md

# Structured JSON extraction with a schema
gx firecrawl scrape "<url>" --format json --schema '{"type":"object","properties":{"title":{"type":"string"}}}' -o .firecrawl/data.json

# Limit PDF page budget
gx firecrawl scrape "<url>.pdf" --max-pages 5 --json -o .firecrawl/report.json
```

## Steps

1. Save scraped content to `.firecrawl/` using `-o` rather than dumping full pages to stdout.
2. Read bounded sections of the saved markdown or JSON file to answer the user's question with clickable source URLs.
3. If a page requires clicks, login, or pagination, switch to `agent-browser` or `firecrawl interact`.

## Gotchas

- Always quote URLs containing `?` or `&`.
- Prefer plain markdown scrape over `--query` to avoid extra credit charges and keep full context inspectable locally.
