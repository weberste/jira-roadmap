# jira-roadmap

Visualize JIRA initiative roadmaps on a timeline.

## What it does

Fetches initiatives from JIRA via JQL, resolves their linked epics, and renders an interactive timeline showing when work starts and ends. Initiatives expand to show individual epic bars. Bars are color-coded by status category (To Do / In Progress / Done).

## How it works

1. User enters a JQL query targeting initiatives (e.g. `type = Initiative AND project = ACME`)
2. App fetches matching issues from JIRA, extracts linked epics via issue links
3. Epics are fetched in bulk to read their start/end date custom fields
4. A timeline is rendered with initiative rows (expandable) and epic rows underneath
5. Timeline bounds are derived from the earliest/latest dates across all epics, with 1-month padding

## Architecture

```
jira_roadmap/
├── config.py        # Reads ~/.jira-roadmap/config.toml (JIRA creds + date field IDs)
├── jira_client.py   # JIRA API: search_roadmap_issues(), list_link_types()
├── models.py        # RoadmapEpic, RoadmapInitiative, RoadmapResult
├── exceptions.py    # Flat hierarchy: RoadmapError → specific errors
├── roadmap.py       # Core logic: fetch_roadmap() + roadmap_result_to_dict()
└── web/
    ├── app.py       # Flask app factory
    ├── routes.py    # GET / (form), POST / (fetch+render), GET /api/link-types
    ├── templates/   # base.html, index.html, partials/error.html
    └── static/      # styles.css, roadmap.js (timeline renderer)
```

## Configuration

`~/.jira-roadmap/config.toml`:

```toml
[jira]
url = "https://yourcompany.atlassian.net"
email = "you@company.com"
api_token = "..."

[roadmap]
start_date_field = "customfield_10015"   # Target Start
end_date_field = "customfield_10016"     # Target End
```

## Key design decisions

- **No CLI** — web-only interface, no typer dependency
- **No changelog parsing** — roadmap only needs summary, status, links, and date fields
- **Dates come from custom fields** — not from sprint or status transitions
- **Initiative dates are derived** — min/max of linked epic dates, not stored on the initiative itself
- **Link type filtering** — optional, allows scoping to specific link types (e.g. only "Relates")
- **Status categories** — uses JIRA's built-in category (new/indeterminate/done) for bar colors
- **Pure JS timeline** — no Chart.js or external visualization library

## Dependencies

`jira`, `tenacity`, `flask`, `python-dateutil`, `tomli-w`

## Running

```bash
uv run --python 3.11 flask --app jira_roadmap.web.app run
```
