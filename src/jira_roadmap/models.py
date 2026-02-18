"""Data models for JIRA Roadmap."""

from dataclasses import dataclass
from datetime import date


@dataclass
class RoadmapEpic:
    """An epic on the roadmap timeline."""

    key: str
    title: str
    status: str
    status_category: str  # "new" | "indeterminate" | "done"
    start_date: date | None
    end_date: date | None
    url: str
    done_stories: int = 0
    cancelled_stories: int = 0
    inprogress_stories: int = 0
    total_stories: int = 0


@dataclass
class RoadmapInitiative:
    """An initiative on the roadmap timeline, containing linked epics."""

    key: str
    title: str
    status: str
    status_category: str
    start_date: date | None  # min of epic start dates
    end_date: date | None  # max of epic end dates
    epics: list[RoadmapEpic]
    url: str


@dataclass
class RoadmapResult:
    """Complete result of a roadmap fetch."""

    initiatives: list[RoadmapInitiative]
    jql_query: str
    timeline_start: date
    timeline_end: date
    jira_url: str
