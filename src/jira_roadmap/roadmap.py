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

    Returns one of: "new", "indeterminate", "done", "cancelled".

    Cancelled statuses share the "done" statusCategory key in JIRA, so we
    detect them by checking the status name before consulting the category.
    """
    if "cancel" in status_field.get("name", "").lower():
        return "cancelled"
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

    # Extract linked epic keys from initiatives, and initiative→initiative dependency links
    epic_keys_set: set[str] = set()
    initiative_epic_links: dict[str, list[str]] = {}  # initiative_key -> [epic_keys]
    initiative_keys_set: set[str] = {issue["key"] for issue in raw_initiatives}
    initiative_deps: list[tuple[str, str]] = []
    seen_init_deps: set[tuple[str, str]] = set()

    for issue in raw_initiatives:
        issue_key = issue["key"]
        fields = issue.get("fields", {})
        issue_links = fields.get("issuelinks", [])
        linked_epics: list[str] = []

        for link in issue_links:
            link_type_name = link.get("type", {}).get("name", "")

            # Collect initiative→initiative dependencies from outward links only
            # (outward-only avoids double-counting since the inward side is the mirror)
            outward = link.get("outwardIssue")
            if outward:
                other_key = outward.get("key", "")
                other_type = outward.get("fields", {}).get("issuetype", {}).get("name", "")
                if other_key and other_key in initiative_keys_set and other_key != issue_key:
                    pair = (issue_key, other_key)
                    if pair not in seen_init_deps:
                        seen_init_deps.add(pair)
                        initiative_deps.append(pair)

            # Check link type filter for epic collection
            if link_types and link_type_name not in link_types:
                continue

            # Check both inward and outward linked issues for epics
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

    # Find additional child epics via the JIRA parent field (company-managed projects
    # with issue hierarchy don't surface these in issuelinks or subtasks).
    initiative_keys = [issue["key"] for issue in raw_initiatives]
    parent_jql = "issueType = Epic AND parent in (" + ", ".join(initiative_keys) + ")"
    try:
        parent_child_epics = client.search_roadmap_issues(parent_jql, date_fields=date_fields)
    except (AuthenticationError, RateLimitError, JiraClientConnectionError, ValueError):
        parent_child_epics = []

    for child in parent_child_epics:
        child_key = child["key"]
        parent_key = child.get("fields", {}).get("parent", {}).get("key", "")
        if parent_key not in initiative_epic_links:
            continue
        existing = initiative_epic_links[parent_key]
        if child_key not in existing:
            existing.append(child_key)
            epic_keys_set.add(child_key)

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

    # Collect epic→epic dependency links from the epics' own issuelinks (outward only)
    epic_deps: list[tuple[str, str]] = []
    seen_epic_deps: set[tuple[str, str]] = set()
    for epic_key, epic_raw in epic_data.items():
        for link in epic_raw.get("fields", {}).get("issuelinks", []):
            outward = link.get("outwardIssue")
            if outward:
                other_key = outward.get("key", "")
                if other_key and other_key in epic_keys_set and other_key != epic_key:
                    pair = (epic_key, other_key)
                    if pair not in seen_epic_deps:
                        seen_epic_deps.add(pair)
                        epic_deps.append(pair)

    # Fetch child stories/tasks for each epic via the parent field.
    # (The subtasks field only captures JIRA Sub-task type issues, not Stories.)
    story_counts: dict[str, dict] = {}
    if epic_keys_set:
        stories_jql = "parent in (" + ", ".join(sorted(epic_keys_set)) + ")"
        try:
            raw_stories = client.search_roadmap_issues(stories_jql, date_fields=[])
        except (AuthenticationError, RateLimitError, JiraClientConnectionError, ValueError):
            raw_stories = []

        for story in raw_stories:
            parent_key = story.get("fields", {}).get("parent", {}).get("key", "")
            if not parent_key or parent_key not in epic_keys_set:
                continue
            counts = story_counts.setdefault(
                parent_key, {"done": 0, "cancelled": 0, "inprogress": 0, "total": 0}
            )
            counts["total"] += 1
            cat = _get_status_category(story.get("fields", {}).get("status", {}))
            if cat == "done":
                counts["done"] += 1
            elif cat == "cancelled":
                counts["cancelled"] += 1
            elif cat == "indeterminate":
                counts["inprogress"] += 1

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

            counts = story_counts.get(epic_key, {})
            done_stories = counts.get("done", 0)
            cancelled_stories = counts.get("cancelled", 0)
            inprogress_stories = counts.get("inprogress", 0)
            total_stories = counts.get("total", 0)

            epic = RoadmapEpic(
                key=epic_key,
                title=epic_fields.get("summary", ""),
                status=epic_status.get("name", ""),
                status_category=_get_status_category(epic_status),
                start_date=epic_start,
                end_date=epic_end,
                url=f"{jira_url}/browse/{epic_key}",
                done_stories=done_stories,
                cancelled_stories=cancelled_stories,
                inprogress_stories=inprogress_stories,
                total_stories=total_stories,
            )
            epics.append(epic)

            if epic_start:
                all_dates.append(epic_start)
            if epic_end:
                all_dates.append(epic_end)

        # Derive initiative dates from epics.
        # If any epic is missing a start or end date we treat that boundary as
        # unknown for the initiative too — we can't claim a definite start when
        # some epics haven't been scheduled yet.
        epic_starts = [e.start_date for e in epics if e.start_date]
        epic_ends = [e.end_date for e in epics if e.end_date]
        all_have_start = epics and all(e.start_date for e in epics)
        all_have_end = epics and all(e.end_date for e in epics)
        init_start = min(epic_starts) if all_have_start else None
        init_end = max(epic_ends) if all_have_end else None

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

    # Collect unique project keys from all initiatives and epics, then resolve names
    all_project_keys: set[str] = set()
    for init in initiatives:
        all_project_keys.add(init.key.split("-")[0])
        for epic in init.epics:
            all_project_keys.add(epic.key.split("-")[0])
    project_names = client.get_project_names(sorted(all_project_keys))

    return RoadmapResult(
        initiatives=initiatives,
        jql_query=jql,
        timeline_start=timeline_start,
        timeline_end=timeline_end,
        jira_url=jira_url,
        initiative_deps=initiative_deps,
        epic_deps=epic_deps,
        project_names=project_names,
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
            "cancelled_stories": e.cancelled_stories,
            "inprogress_stories": e.inprogress_stories,
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
        "initiative_deps": [[a, b] for a, b in result.initiative_deps],
        "epic_deps": [[a, b] for a, b in result.epic_deps],
        "project_names": result.project_names,
    }
