# jira-roadmap

Visualize JIRA initiative roadmaps on an interactive timeline.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A JIRA Cloud instance with API access

## Setup

### 1. Clone and install

```bash
git clone git@github.com:weberste/jira-roadmap.git
cd jira-roadmap
uv sync --python 3.11
```

Or with pip:

```bash
pip install -e .
```

### 2. Configure JIRA credentials

Create `~/.jira-roadmap/config.toml`:

```bash
mkdir -p ~/.jira-roadmap
cat > ~/.jira-roadmap/config.toml << 'EOF'
[jira]
url = "https://yourcompany.atlassian.net"
email = "you@company.com"
api_token = "your-api-token"

[roadmap]
start_date_field = "customfield_10015"
end_date_field = "customfield_10016"
EOF
```

**Finding your custom field IDs:** In JIRA, go to an epic that has Target Start / Target End dates set, then use the REST API to inspect its fields:

```
https://yourcompany.atlassian.net/rest/api/2/issue/EPIC-123
```

Look for fields like `customfield_10015` whose values match the dates you see in the UI.

**API token:** Generate one at https://id.atlassian.com/manage-profile/security/api-tokens

## Running

```bash
uv run flask --app jira_roadmap.web.app run
```

Then open http://127.0.0.1:5000 in your browser.

To bind to a specific host/port (e.g. to access from other machines):

```bash
uv run flask --app jira_roadmap.web.app run --host 0.0.0.0 --port 8080
```

## Usage

1. Enter a JQL query that returns initiatives, e.g. `type = Initiative AND project = ACME`
2. Optionally filter by link type (comma-separated)
3. Click **Load Roadmap**
4. Click an initiative row to expand/collapse its linked epics
5. Use the **Initiatives** and **Epics** dropdowns to filter by status category or project
6. Use the **Dependencies** button to show/hide dependency arrows between items

A built-in demo with no JIRA credentials is available at http://127.0.0.1:5000/demo.

## Running tests

```bash
uv run pytest tests/ -v
```
