# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Install dependencies:**
```bash
uv sync --python 3.11
```

**Run the app:**
```bash
uv run flask --app jira_roadmap.web.app run
```

**Run tests:**
```bash
uv run pytest tests/ -v
```

**Run a single test:**
```bash
uv run pytest tests/test_roadmap.py::test_function_name -v
```

**Lint and format:**
```bash
uv run ruff check src/
uv run ruff format src/
```

## Architecture

The app fetches JIRA initiatives via JQL and renders them as an interactive timeline. Initiative dates are **derived** from their linked epics (min start / max end), not stored on the initiative itself.

**Data flow:**
1. User submits JQL query via web form
2. `routes.py` calls `fetch_roadmap(jql, link_types)` in `roadmap.py`
3. `roadmap.py` loads config from `~/.jira-roadmap/config.toml`, queries JIRA, derives initiative dates from epics
4. Result is serialized to dict and passed to the template
5. Template embeds JSON data; `roadmap.js` calls `initRoadmap(data)` to render the pure-JS timeline

**Key modules:**
- `src/jira_roadmap/roadmap.py` — core business logic: fetches initiatives, resolves linked epics, derives dates
- `src/jira_roadmap/jira_client.py` — JIRA API wrapper with tenacity retry/backoff
- `src/jira_roadmap/config.py` — loads and validates `~/.jira-roadmap/config.toml`
- `src/jira_roadmap/web/routes.py` — Flask route handlers (`GET/POST /`, `/api/link-types`, `/health`)
- `src/jira_roadmap/web/static/js/roadmap.js` — pure JS timeline rendering (no external libraries)

**Config file** (`~/.jira-roadmap/config.toml`) stores JIRA credentials and custom field IDs for start/end dates. The `RoadmapConfigError` exception is raised when date fields aren't configured.

**Status colors** use JIRA's built-in status categories: `new` → gray, `indeterminate` → blue, `done` → green.

**Ruff config:** 100-char line length, Python 3.11 target, E/F/I/N/W rules enabled.
