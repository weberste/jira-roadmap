"""Tests for roadmap data fetching and processing."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from jira_roadmap.exceptions import (
    ConfigNotFoundError,
    InvalidConfigError,
    NoIssuesFoundError,
    RoadmapConfigError,
)
from jira_roadmap.models import RoadmapEpic, RoadmapInitiative, RoadmapResult
from jira_roadmap.roadmap import (
    _get_status_category,
    _parse_date_field,
    fetch_roadmap,
    roadmap_result_to_dict,
)


class TestParseDateField:
    """Tests for _parse_date_field helper."""

    def test_parses_iso_date(self):
        fields = {"cf_start": "2026-03-15"}
        assert _parse_date_field(fields, "cf_start") == date(2026, 3, 15)

    def test_parses_datetime_string(self):
        fields = {"cf_start": "2026-03-15T10:30:00.000+0000"}
        assert _parse_date_field(fields, "cf_start") == date(2026, 3, 15)

    def test_returns_none_for_missing_field(self):
        assert _parse_date_field({}, "cf_start") is None

    def test_returns_none_for_none_value(self):
        assert _parse_date_field({"cf_start": None}, "cf_start") is None

    def test_returns_none_for_invalid_value(self):
        assert _parse_date_field({"cf_start": "not-a-date"}, "cf_start") is None


class TestGetStatusCategory:
    """Tests for _get_status_category helper."""

    def test_returns_new(self):
        status = {"statusCategory": {"key": "new", "name": "To Do"}}
        assert _get_status_category(status) == "new"

    def test_returns_indeterminate(self):
        status = {"statusCategory": {"key": "indeterminate", "name": "In Progress"}}
        assert _get_status_category(status) == "indeterminate"

    def test_returns_done(self):
        status = {"statusCategory": {"key": "done", "name": "Done"}}
        assert _get_status_category(status) == "done"

    def test_falls_back_to_name_done(self):
        status = {"statusCategory": {"key": "unknown", "name": "Done"}}
        assert _get_status_category(status) == "done"

    def test_falls_back_to_name_progress(self):
        status = {"statusCategory": {"key": "unknown", "name": "In Progress"}}
        assert _get_status_category(status) == "indeterminate"

    def test_defaults_to_new(self):
        status = {"statusCategory": {"key": "unknown", "name": "Unknown"}}
        assert _get_status_category(status) == "new"

    def test_handles_empty_status(self):
        assert _get_status_category({}) == "new"


def _make_config(start_field="cf_10015", end_field="cf_10016"):
    """Create a mock config with roadmap fields."""
    config = MagicMock()
    config.start_date_field = start_field
    config.end_date_field = end_field
    config.jira_url = "https://jira.example.com"
    return config


def _make_initiative_issue(key, summary, epic_links=None):
    """Build a raw initiative issue dict with optional epic links."""
    links = []
    for epic_key in (epic_links or []):
        links.append({
            "type": {"name": "Relates"},
            "outwardIssue": {
                "key": epic_key,
                "fields": {
                    "issuetype": {"name": "Epic"},
                    "summary": f"Epic {epic_key}",
                },
            },
        })
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "issuetype": {"name": "Initiative"},
            "status": {
                "name": "In Progress",
                "statusCategory": {"key": "indeterminate", "name": "In Progress"},
            },
            "issuelinks": links,
        },
    }


def _make_epic_issue(key, summary, start_date=None, end_date=None):
    """Build a raw epic issue dict."""
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "issuetype": {"name": "Epic"},
            "status": {
                "name": "To Do",
                "statusCategory": {"key": "new", "name": "To Do"},
            },
            "issuelinks": [],
            "cf_10015": start_date,
            "cf_10016": end_date,
        },
    }


class TestFetchRoadmap:
    """Tests for fetch_roadmap function."""

    @patch("jira_roadmap.roadmap.config_exists", return_value=False)
    def test_raises_when_no_config(self, mock_exists):
        with pytest.raises(ConfigNotFoundError):
            fetch_roadmap("type = Initiative")

    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_raises_when_invalid_config(self, mock_exists, mock_load):
        mock_load.side_effect = ValueError("bad config")
        with pytest.raises(InvalidConfigError):
            fetch_roadmap("type = Initiative")

    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_raises_when_roadmap_fields_missing(self, mock_exists, mock_load):
        config = MagicMock()
        config.start_date_field = None
        config.end_date_field = None
        mock_load.return_value = config
        with pytest.raises(RoadmapConfigError, match="not configured"):
            fetch_roadmap("type = Initiative")

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_raises_when_no_issues(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()
        mock_client.search_roadmap_issues.return_value = []
        mock_jira_cls.return_value = mock_client

        with pytest.raises(NoIssuesFoundError):
            fetch_roadmap("type = Initiative")

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_builds_initiatives_with_epics(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()

        initiatives = [
            _make_initiative_issue("INIT-1", "Initiative One", ["EPIC-1", "EPIC-2"]),
        ]
        epics = [
            _make_epic_issue("EPIC-1", "Epic One", "2026-01-01", "2026-03-31"),
            _make_epic_issue("EPIC-2", "Epic Two", "2026-02-15", "2026-06-30"),
        ]

        def search_side_effect(jql, **kwargs):
            if "INIT" in jql or "Initiative" in jql:
                return initiatives
            return epics

        mock_client.search_roadmap_issues.side_effect = search_side_effect
        mock_jira_cls.return_value = mock_client

        result = fetch_roadmap("type = Initiative")

        assert len(result.initiatives) == 1
        init = result.initiatives[0]
        assert init.key == "INIT-1"
        assert len(init.epics) == 2
        assert init.start_date == date(2026, 1, 1)
        assert init.end_date == date(2026, 6, 30)
        assert init.status_category == "indeterminate"

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_filters_by_link_type(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()

        # Initiative with Relates and Blocks links
        init_issue = {
            "key": "INIT-1",
            "fields": {
                "summary": "Test",
                "issuetype": {"name": "Initiative"},
                "status": {
                    "name": "To Do",
                    "statusCategory": {"key": "new", "name": "To Do"},
                },
                "issuelinks": [
                    {
                        "type": {"name": "Relates"},
                        "outwardIssue": {
                            "key": "EPIC-1",
                            "fields": {"issuetype": {"name": "Epic"}, "summary": "E1"},
                        },
                    },
                    {
                        "type": {"name": "Blocks"},
                        "outwardIssue": {
                            "key": "EPIC-2",
                            "fields": {"issuetype": {"name": "Epic"}, "summary": "E2"},
                        },
                    },
                ],
            },
        }

        epic1 = _make_epic_issue("EPIC-1", "E1", "2026-01-01", "2026-03-31")

        def search_side_effect(jql, **kwargs):
            if "Initiative" in jql:
                return [init_issue]
            # Only EPIC-1 should be fetched
            return [epic1]

        mock_client.search_roadmap_issues.side_effect = search_side_effect
        mock_jira_cls.return_value = mock_client

        result = fetch_roadmap("type = Initiative", link_types=["Relates"])

        init = result.initiatives[0]
        # Only EPIC-1 via "Relates" link, not EPIC-2 via "Blocks"
        assert len(init.epics) == 1
        assert init.epics[0].key == "EPIC-1"

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_collects_epics_from_child_work_items(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()

        # Initiative with one linked epic and one child epic (subtask hierarchy)
        init_issue = {
            "key": "INIT-1",
            "fields": {
                "summary": "Test",
                "issuetype": {"name": "Initiative"},
                "status": {
                    "name": "In Progress",
                    "statusCategory": {"key": "indeterminate", "name": "In Progress"},
                },
                "issuelinks": [
                    {
                        "type": {"name": "Relates"},
                        "outwardIssue": {
                            "key": "EPIC-1",
                            "fields": {"issuetype": {"name": "Epic"}, "summary": "Linked Epic"},
                        },
                    },
                ],
                "subtasks": [
                    {
                        "key": "EPIC-2",
                        "fields": {"issuetype": {"name": "Epic"}, "summary": "Child Epic"},
                    },
                    {
                        "key": "STORY-1",
                        "fields": {"issuetype": {"name": "Story"}, "summary": "Not an epic"},
                    },
                ],
            },
        }

        epic1 = _make_epic_issue("EPIC-1", "Linked Epic", "2026-01-01", "2026-03-31")
        epic2 = _make_epic_issue("EPIC-2", "Child Epic", "2026-04-01", "2026-06-30")

        def search_side_effect(jql, **kwargs):
            if "Initiative" in jql:
                return [init_issue]
            return [epic1, epic2]

        mock_client.search_roadmap_issues.side_effect = search_side_effect
        mock_jira_cls.return_value = mock_client

        result = fetch_roadmap("type = Initiative")

        init = result.initiatives[0]
        assert len(init.epics) == 2
        epic_keys = {e.key for e in init.epics}
        assert epic_keys == {"EPIC-1", "EPIC-2"}
        assert init.start_date == date(2026, 1, 1)
        assert init.end_date == date(2026, 6, 30)

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_collects_epics_via_parent_field(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()

        # Initiative with no issuelinks and no subtasks — epics are children via parent field
        init_issue = {
            "key": "INIT-1",
            "fields": {
                "summary": "Test",
                "issuetype": {"name": "Initiative"},
                "status": {
                    "name": "In Progress",
                    "statusCategory": {"key": "indeterminate", "name": "In Progress"},
                },
                "issuelinks": [],
                "subtasks": [],
            },
        }

        # Returned by the parent-field JQL query
        child_epic_raw = {
            "key": "EPIC-1",
            "fields": {
                "summary": "Child Epic via Parent",
                "issuetype": {"name": "Epic"},
                "status": {
                    "name": "To Do",
                    "statusCategory": {"key": "new", "name": "To Do"},
                },
                "issuelinks": [],
                "subtasks": [],
                "parent": {"key": "INIT-1"},
                "cf_10015": "2026-03-01",
                "cf_10016": "2026-06-30",
            },
        }

        epic_detail = _make_epic_issue("EPIC-1", "Child Epic via Parent", "2026-03-01", "2026-06-30")

        def search_side_effect(jql, **kwargs):
            if "Initiative" in jql:
                return [init_issue]
            if "parent in" in jql:
                return [child_epic_raw]
            return [epic_detail]

        mock_client.search_roadmap_issues.side_effect = search_side_effect
        mock_jira_cls.return_value = mock_client

        result = fetch_roadmap("type = Initiative")

        init = result.initiatives[0]
        assert len(init.epics) == 1
        assert init.epics[0].key == "EPIC-1"
        assert init.start_date is not None
        assert init.end_date is not None

    @patch("jira_roadmap.roadmap.JiraClient")
    @patch("jira_roadmap.roadmap.load_config")
    @patch("jira_roadmap.roadmap.config_exists", return_value=True)
    def test_initiative_without_epics(self, mock_exists, mock_load, mock_jira_cls):
        mock_load.return_value = _make_config()
        mock_client = MagicMock()

        initiatives = [_make_initiative_issue("INIT-1", "Lonely Initiative", [])]

        mock_client.search_roadmap_issues.return_value = initiatives
        mock_jira_cls.return_value = mock_client

        result = fetch_roadmap("type = Initiative")
        init = result.initiatives[0]
        assert len(init.epics) == 0
        assert init.start_date is None
        assert init.end_date is None


class TestRoadmapResultToDict:
    """Tests for roadmap_result_to_dict serializer."""

    def test_serializes_result(self):
        result = RoadmapResult(
            initiatives=[
                RoadmapInitiative(
                    key="INIT-1",
                    title="Test Initiative",
                    status="In Progress",
                    status_category="indeterminate",
                    start_date=date(2026, 1, 1),
                    end_date=date(2026, 6, 30),
                    epics=[
                        RoadmapEpic(
                            key="EPIC-1",
                            title="Test Epic",
                            status="To Do",
                            status_category="new",
                            start_date=date(2026, 1, 1),
                            end_date=date(2026, 3, 31),
                            url="https://jira.example.com/browse/EPIC-1",
                        ),
                    ],
                    url="https://jira.example.com/browse/INIT-1",
                ),
            ],
            jql_query="type = Initiative",
            timeline_start=date(2025, 12, 1),
            timeline_end=date(2026, 8, 1),
            jira_url="https://jira.example.com",
        )

        d = roadmap_result_to_dict(result)

        assert d["timeline_start"] == "2025-12-01"
        assert d["timeline_end"] == "2026-08-01"
        assert len(d["initiatives"]) == 1
        init = d["initiatives"][0]
        assert init["key"] == "INIT-1"
        assert init["start_date"] == "2026-01-01"
        assert len(init["epics"]) == 1
        assert init["epics"][0]["key"] == "EPIC-1"
        assert init["epics"][0]["start_date"] == "2026-01-01"

    def test_handles_none_dates(self):
        result = RoadmapResult(
            initiatives=[
                RoadmapInitiative(
                    key="INIT-1",
                    title="No Dates",
                    status="To Do",
                    status_category="new",
                    start_date=None,
                    end_date=None,
                    epics=[],
                    url="https://jira.example.com/browse/INIT-1",
                ),
            ],
            jql_query="type = Initiative",
            timeline_start=date(2026, 1, 1),
            timeline_end=date(2026, 12, 31),
            jira_url="https://jira.example.com",
        )

        d = roadmap_result_to_dict(result)
        init = d["initiatives"][0]
        assert init["start_date"] is None
        assert init["end_date"] is None


class TestRoadmapRoutes:
    """Tests for roadmap HTTP route handlers."""

    def setup_method(self):
        from jira_roadmap.web.app import create_app
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_get_index_renders(self):
        with patch("jira_roadmap.web.routes.config_exists", return_value=True):
            resp = self.client.get("/")
        assert resp.status_code == 200
        assert b"Roadmap" in resp.data or b"roadmap" in resp.data

    def test_post_requires_jql(self):
        with patch("jira_roadmap.web.routes.config_exists", return_value=True):
            resp = self.client.post("/", data={"jql": ""})
        assert resp.status_code == 400

    @patch("jira_roadmap.web.routes.fetch_roadmap")
    @patch("jira_roadmap.web.routes.roadmap_result_to_dict")
    @patch("jira_roadmap.web.routes.config_exists", return_value=True)
    def test_post_success(self, mock_exists, mock_to_dict, mock_fetch):
        mock_result = MagicMock()
        mock_result.initiatives = []
        mock_fetch.return_value = mock_result
        mock_to_dict.return_value = {
            "initiatives": [],
            "timeline_start": "2026-01-01",
            "timeline_end": "2026-12-31",
            "jql_query": "test",
            "jira_url": "https://jira.example.com",
        }

        resp = self.client.post("/", data={"jql": "type = Initiative"})
        assert resp.status_code == 200

    @patch("jira_roadmap.web.routes.config_exists", return_value=False)
    def test_api_link_types_no_config(self, mock_exists):
        resp = self.client.get("/api/link-types")
        assert resp.status_code == 503
