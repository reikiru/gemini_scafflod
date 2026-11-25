---
name: web-search-api
description: Run fast web search via Tavily and semantic search via Exa using the bundled tools/web-search CLI over the local file bridge. Use when the user asks to search with Tavily or Exa, wants quick grounded web snippets, or wants semantic/neural discovery across articles and docs.
---
# web-search-api

Unified interface to Tavily and Exa web search APIs via the zero-dependency `tools/web-search` CLI bundled in `gemini_scaffold`.

## Bridge Execution

Run `web-search` through `bridge/gx` (with `web-search` allowlisted in `bridge/allowlist.conf` and `TAVILY_API_KEY` / `EXA_API_KEY` set in host-side `bridge/env.conf`). API keys remain strictly on the host side.

## Quick Start

```bash
# Tavily web search (quick factual and current-events search with summary)
gx web-search tavily "latest macOS launchd changes" --max-results 5

# Tavily deeper search with raw JSON
gx web-search tavily "your query" --depth advanced --json

# Exa semantic search with extracted text snippets
gx web-search exa "minimalist sandbox bridge architectures" --num-results 5 --type neural --contents

# Exa raw JSON output
gx web-search exa "your query" --type auto --contents --json
```

## When to Pick Which Engine

- **Tavily**: Fast general web search, current events, and concise answer summaries.
- **Exa**: Semantic and neural discovery for technical blog posts, research articles, and niche documentation.
- **Firecrawl**: Use `firecrawl-scrape` when you already have a URL and need full Markdown or JSON extraction.

## Gotchas

- If exit code is 2, check that `TAVILY_API_KEY` or `EXA_API_KEY` is populated in host-side `bridge/env.conf` (run `bash scripts/bootstrap-env.sh` on the host to sync from shell config).
- Always preserve returned URLs as clickable links when summarizing results.
