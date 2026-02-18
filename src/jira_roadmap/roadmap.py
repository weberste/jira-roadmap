"""Roadmap data fetching and processing."""

from datetime import date, timedelta

from jira_roadmap.config import config_exists, load_config
from jira_roadmap.exceptions import (
    ConfigNotFoundError,
    InvalidConfigError,
    InvalidJqlError,
    JiraAuthError,
    JiraConnectionError,
    JiraRateLimitError,
    NoIssuesFoundError,
    RoadmapConfigError,
)
from jira_roadmap.jira_client import (
    AuthenticationError,
    JiraClient,
    RateLimitError,
)
from jira_roadmap.jira_client import (
    ConnectionError as JiraClientConnectionError,
)
from jira_roadmap.models import (
    RoadmapEpic,
    RoadmapInitiative,
    RoadmapResult,
)


def _parse_date_field(fields: dict, field_id: str) -> date | None:
    """Parse a JIRA custom date field value to a date object."""
    value = fields.get(field_id)
    if not value:
        return None
    try:
        # JIRA date fields are typically "YYYY-MM-DD"
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _get_status_category(status_field: dict) -> str:
    """Extract the status category key from a JIRA status field.

    Returns one of: "new", "indeterminate", "done".
    """
    category = status_field.get("statusCategory", {})
    key = category.get("key", "").lower()
    if key in ("new", "indeterminate", "done"):
        return key
    # Fallback based on category name
    name = category.get("name", "").lower()
    if "done" in name:
        return "done"
    if "progress" in name or "indeterminate" in name:
        return "indeterminate"
    return "new"


def fetch_roadmap(jql: str, link_types: list[str] | None = None) -> RoadmapResult:
    """Fetch roadmap data from JIRA.

    Args:
        jql: JQL query for finding initiatives
        link_types: Optional list of link type names to filter by

    Returns:
        RoadmapResult with initiatives and their linked epics

    Raises:
        ConfigNotFoundError: If config file not found
        InvalidConfigError: If config is invalid
        RoadmapConfigError: If roadmap date fields not configured
        JiraAuthError: If JIRA authentication fails
        JiraRateLimitError: If rate limited
        JiraConnectionError: If cannot connect
        InvalidJqlError: If JQL is invalid
        NoIssuesFoundError: If no issues match query
    """
    # Load configuration
    if not config_exists():
        raise ConfigNotFoundError(
            "Configuration not found. Create ~/.jira-roadmap/config.toml to set up."
        )

    try:
        config = load_config()
    except ValueError as e:
        raise InvalidConfigError(f"Invalid configuration: {e}")

    # Validate roadmap fields are configured
    if not config.start_date_field or not config.end_date_field:
        raise RoadmapConfigError(
            "Roadmap date fields are not configured. Add [roadmap] section to "
            "~/.jira-roadmap/config.toml with start_date_field and end_date_field."
        )

    start_field = config.start_date_field
    end_field = config.end_date_field
    date_fields = [start_field, end_field]

    client = JiraClient(config)

    # Fetch initiatives
    try:
        raw_initiatives = client.search_roadmap_issues(jql, date_fields=date_fields)
    except AuthenticationError:
        raise JiraAuthError(
            "JIRA authentication failed. Check your credentials in "
            "~/.jira-roadmap/config.toml."
        )
    except RateLimitError:
        raise JiraRateLimitError(
            "JIRA rate limit exceeded. Please wait a moment and try again."
        )
    except JiraClientConnectionError as e:
        raise JiraConnectionError(str(e))
    except ValueError as e:
        raise InvalidJqlError(f"Invalid JQL query: {e}. Check your query syntax.")

    if not raw_initiatives:
        raise NoIssuesFoundError("No issues found matching your query.")

    jira_url = config.jira_url.rstrip("/")

    # Extract linked epic keys from initiatives
    epic_keys_set: set[str] = set()
    initiative_epic_links: dict[str, list[str]] = {}  # initiative_key -> [epic_keys]

    for issue in raw_initiatives:
        issue_key = issue["key"]
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        linked_epics: list[str] = []

        for link in issue_links:
            # Check link type filter
            link_type_name = link.get("type", {}).get("name", "")
            if link_types and link_type_name not in link_types:
                continue

            # Check both inward and outward linked issues
            for direction in ("inwardIssue", "outwardIssue"):
                linked_issue = link.get(direction)
                if not linked_issue:
                    continue
                linked_type = linked_issue.get("fields", {}).get("issuetype", {}).get("name", "")
                if linked_type == "Epic":
                    linked_key = linked_issue.get("key", "")
                    if linked_key:
                        linked_epics.append(linked_key)
                        epic_keys_set.add(linked_key)

        # Also collect epics from child work items (parent-child hierarchy)
        for subtask in fields.get("subtasks", []):
            subtask_type = subtask.get("fields", {}).get("issuetype", {}).get("name", "")
            if subtask_type == "Epic":
                subtask_key = subtask.get("key", "")
                if subtask_key and subtask_key not in linked_epics:
                    linked_epics.append(subtask_key)
                    epic_keys_set.add(subtask_key)

        initiative_epic_links[issue_key] = linked_epics

    # Fetch epics in bulk if any were found
    epic_data: dict[str, dict] = {}
    if epic_keys_set:
        epic_keys_jql = "key in (" + ", ".join(sorted(epic_keys_set)) + ")"
        try:
            raw_epics = client.search_roadmap_issues(epic_keys_jql, date_fields=date_fields)
        except (AuthenticationError, RateLimitError, JiraClientConnectionError, ValueError):
            # If epic fetch fails, continue without epic details
            raw_epics = []

        for epic in raw_epics:
            epic_data[epic["key"]] = epic

    # Build RoadmapInitiative objects
    initiatives: list[RoadmapInitiative] = []
    all_dates: list[date] = []

    for issue in raw_initiatives:
        issue_key = issue["key"]
        fields = issue.get("fields", {})
        status_field = fields.get("status", {})

        # Build epics for this initiative
        epics: list[RoadmapEpic] = []
        for epic_key in initiative_epic_links.get(issue_key, []):
            epic_raw = epic_data.get(epic_key)
            if not epic_raw:
                continue
            epic_fields = epic_raw.get("fields", {})
            epic_status = epic_fields.get("status", {})
            epic_start = _parse_date_field(epic_fields, start_field)
            epic_end = _parse_date_field(epic_fields, end_field)

            # Count child stories/tasks from JIRA parent-child hierarchy
            done_stories = 0
            total_stories = 0
            for subtask in epic_fields.get("subtasks", []):
                subtask_status = subtask.get("fields", {}).get("status", {})
                total_stories += 1
                if _get_status_category(subtask_status) == "done":
                    done_stories += 1

            epic = RoadmapEpic(
                key=epic_key,
                title=epic_fields.get("summary", ""),
                status=epic_status.get("name", ""),
                status_category=_get_status_category(epic_status),
                start_date=epic_start,
                end_date=epic_end,
                url=f"{jira_url}/browse/{epic_key}",
                done_stories=done_stories,
                total_stories=total_stories,
            )
            epics.append(epic)

            if epic_start:
                all_dates.append(epic_start)
            if epic_end:
                all_dates.append(epic_end)

        # Derive initiative dates from epics
        epic_starts = [e.start_date for e in epics if e.start_date]
        epic_ends = [e.end_date for e in epics if e.end_date]
        init_start = min(epic_starts) if epic_starts else None
        init_end = max(epic_ends) if epic_ends else None

        if init_start:
            all_dates.append(init_start)
        if init_end:
            all_dates.append(init_end)

        initiative = RoadmapInitiative(
            key=issue_key,
            title=fields.get("summary", ""),
            status=status_field.get("name", ""),
            status_category=_get_status_category(status_field),
            start_date=init_start,
            end_date=init_end,
            epics=epics,
            url=f"{jira_url}/browse/{issue_key}",
        )
        initiatives.append(initiative)

    # Calculate timeline bounds
    today = date.today()
    if all_dates:
        timeline_start = min(all_dates)
        timeline_end = max(all_dates)
    else:
        # No dates found - default to current year
        timeline_start = today.replace(month=1, day=1)
        timeline_end = today.replace(month=12, day=31)

    # Ensure the timeline always extends at least 9 months into the future
    future_month = today.month + 9
    nine_months_out = date(today.year + (future_month - 1) // 12, (future_month - 1) % 12 + 1, 1)
    if timeline_end < nine_months_out:
        timeline_end = nine_months_out

    # Add padding: 1 month before and after
    timeline_start = (timeline_start.replace(day=1) - timedelta(days=1)).replace(day=1)
    timeline_end = (timeline_end.replace(day=28) + timedelta(days=5)).replace(day=1)

    return RoadmapResult(
        initiatives=initiatives,
        jql_query=jql,
        timeline_start=timeline_start,
        timeline_end=timeline_end,
        jira_url=jira_url,
    )


def roadmap_result_to_dict(result: RoadmapResult) -> dict:
    """Convert RoadmapResult to a JSON-serializable dict for the template."""

    def _date_str(d: date | None) -> str | None:
        return d.isoformat() if d else None

    def _epic_dict(e: RoadmapEpic) -> dict:
        return {
            "key": e.key,
            "title": e.title,
            "status": e.status,
            "status_category": e.status_category,
            "start_date": _date_str(e.start_date),
            "end_date": _date_str(e.end_date),
            "url": e.url,
            "done_stories": e.done_stories,
            "total_stories": e.total_stories,
        }

    initiatives = []
    for init in result.initiatives:
        initiatives.append({
            "key": init.key,
            "title": init.title,
            "status": init.status,
            "status_category": init.status_category,
            "start_date": _date_str(init.start_date),
            "end_date": _date_str(init.end_date),
            "epics": [_epic_dict(e) for e in init.epics],
            "url": init.url,
        })

    return {
        "initiatives": initiatives,
        "jql_query": result.jql_query,
        "timeline_start": result.timeline_start.isoformat(),
        "timeline_end": result.timeline_end.isoformat(),
        "jira_url": result.jira_url,
    }
