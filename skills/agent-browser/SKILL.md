---
name: agent-browser
description: Browser automation CLI for AI agents via the local file bridge. Use when the user needs to interact with websites, open pages, fill forms, click buttons, take screenshots, scrape dynamic web apps, automate Electron desktop apps, or run QA and exploratory browser testing.
---
# agent-browser

Fast browser automation CLI using Chrome/Chromium via CDP with accessibility-tree snapshots and compact element refs (`@eN`).

## Bridge Execution

Run `agent-browser` through the local file bridge client (`$GX_BIN` or `bridge/gx` in `gemini_scaffold`) so it executes outside the sandbox without network approval prompts. Ensure `agent-browser` is allowlisted in `bridge/allowlist.conf`.

## Start Here

Before running browser commands, load the CLI's built-in workflow guide matching the installed version:

```bash
gx agent-browser skills get core
gx agent-browser skills get core --full
```

## Specialized Workflows

Load specialized guides from the CLI when needed:

- Electron desktop apps: `gx agent-browser skills get electron`
- Exploratory QA and dogfooding: `gx agent-browser skills get dogfood`
- HAR capture and API client derivation: `gx agent-browser skills get derive-client`
- List all installed guides: `gx agent-browser skills list`

## Gotchas

- Always verify `gx ping` succeeds before starting a multi-step browser session.
- For long-lived browser sessions or watchers, use `gx bg` and stop them with `gx kill <job_id>` when finished.
