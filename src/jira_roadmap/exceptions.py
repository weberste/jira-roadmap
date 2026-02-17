"""Exception hierarchy for JIRA Roadmap."""


class RoadmapError(Exception):
    """Base exception for roadmap errors."""

    pass


class ConfigNotFoundError(RoadmapError):
    """Configuration file not found."""

    pass


class InvalidConfigError(RoadmapError):
    """Configuration is invalid."""

    pass


class JiraAuthError(RoadmapError):
    """JIRA authentication failed."""

    pass


class JiraConnectionError(RoadmapError):
    """Cannot connect to JIRA server."""

    pass


class JiraRateLimitError(RoadmapError):
    """JIRA rate limit exceeded."""

    pass


class InvalidJqlError(RoadmapError):
    """Invalid JQL query."""

    pass


class NoIssuesFoundError(RoadmapError):
    """No issues found matching query."""

    pass


class RoadmapConfigError(RoadmapError):
    """Roadmap date fields not configured."""

    pass
