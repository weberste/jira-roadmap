# jira-roadmap

Visualize JIRA initiative roadmaps on a timeline.

## What it does

Fetches initiatives from JIRA via JQL, resolves their linked epics, and renders an interactive timeline showing when work starts and ends. Initiatives expand to show individual epic bars. Bars are color-coded by status category (To Do / In Progress / Done). Dependency arrows connect initiatives to other initiatives and epics to other epics. Filter dropdowns let you show/hide rows by status category and by project.

## How it works

1. User enters a JQL query targeting initiatives (e.g. `type = Initiative AND project = ACME`)
2. App fetches matching issues from JIRA, extracts epics via issue links and child work items (subtask hierarchy)
3. Epics are fetched in bulk to read their start/end date custom fields
4. Project names are resolved from the JIRA project API for all unique project keys found in the result
5. A timeline is rendered with initiative rows (expandable) and epic rows underneath
6. Timeline bounds are derived from the earliest/latest dates across all epics, with 1-month padding

## Architecture

```
jira_roadmap/
├── config.py        # Reads ~/.jira-roadmap/config.toml (JIRA creds + date field IDs)
├── jira_client.py   # JIRA API: search_roadmap_issues(), list_link_types(), get_project_names()
├── models.py        # RoadmapEpic, RoadmapInitiative, RoadmapResult
├── exceptions.py    # Flat hierarchy: RoadmapError → specific errors
├── roadmap.py       # Core logic: fetch_roadmap() + roadmap_result_to_dict()
└── web/
    ├── app.py       # Flask app factory
    ├── routes.py    # GET / (form), POST / (fetch+render), GET /demo, GET /api/link-types
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
- **Initiative dates are derived** — min/max of epic dates, not stored on the initiative itself; if any epic is missing a date boundary the initiative shows none on that side
- **Epics collected two ways** — via issue links (subject to link type filter) and via parent-child hierarchy (`subtasks` field + `parent` field JQL, always included)
- **Link type filtering** — optional, scopes which issue link types are followed for epic collection (e.g. only "Relates"); does not affect child work items or dependency arrows
- **Dependency arrows** — all outward issue links between same-type items (initiative→initiative, epic→epic) are rendered as bezier arrows; hidden by default, toggled via the Dependencies button; hidden when either endpoint is filtered/collapsed
- **Status categories** — uses JIRA's built-in category (new/indeterminate/done) for bar colors; cancelled statuses are detected by name since JIRA maps them to the "done" category key
- **Filter dropdowns** — Initiatives and Epics each have a dropdown with two sections: Status (To Do / In Progress / Done / Cancelled) and Project (one entry per unique project key, resolved to human-readable names via the JIRA project API)
- **Project name resolution** — project keys are extracted from issue key prefixes, then resolved to display names via `JiraClient.get_project_names()`; falls back to the raw key on error
- **Pure JS timeline** — no Chart.js or external visualization library
- **Demo route** — `GET /demo` renders a fully self-contained example with no JIRA credentials required

## Dependencies

`jira`, `tenacity`, `flask`, `tomli-w`

## Running

```bash
uv run flask --app jira_roadmap.web.app run
```
