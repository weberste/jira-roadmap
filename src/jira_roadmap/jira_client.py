"""JIRA API client with retry logic."""

from jira import JIRA, JIRAError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jira_roadmap.config import Config


class RateLimitError(Exception):
    """Raised when JIRA API rate limit is hit."""

    pass


class AuthenticationError(Exception):
    """Raised when JIRA authentication fails."""

    pass


class ConnectionError(Exception):
    """Raised when JIRA server cannot be reached."""

    pass


class JiraClient:
    """Client for interacting with JIRA Cloud API."""

    def __init__(self, config: Config) -> None:
        """Initialize JIRA client with configuration."""
        self.config = config
        self._client: JIRA | None = None

    def _get_client(self) -> JIRA:
        """Get or create JIRA client instance."""
        if self._client is None:
            try:
                self._client = JIRA(
                    server=self.config.jira_url,
                    basic_auth=(self.config.jira_email, self.config.jira_api_token),
                    timeout=15,
                )
            except JIRAError as e:
                if e.status_code == 401:
                    raise AuthenticationError(
                        "Authentication failed. Check your email and API token."
                    ) from e
                raise
            except Exception as e:
                error_msg = str(e).lower()
                if "connection" in error_msg or "resolve" in error_msg or "timeout" in error_msg:
                    raise ConnectionError(
                        f"Cannot connect to JIRA server at {self.config.jira_url}. "
                        "Check the URL and your network connection."
                    ) from e
                raise
        return self._client

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True,
    )
    def search_roadmap_issues(self, jql: str, date_fields: list[str] | None = None) -> list[dict]:
        """Search for issues relevant to roadmap visualization.

        Args:
            jql: JQL query string
            date_fields: Custom field IDs for start/end dates

        Returns:
            List of raw issue dicts

        Raises:
            RateLimitError: If rate limited (will be retried)
            AuthenticationError: If authentication fails
            JIRAError: For other JIRA API errors
        """
        client = self._get_client()

        try:
            fields = ["summary", "issuetype", "status", "issuelinks", "subtasks", "parent"]
            if date_fields:
                fields.extend(date_fields)

            result = client.enhanced_search_issues(
                jql,
                maxResults=0,
                fields=fields,
            )

            return [self._issue_to_dict(issue) for issue in result]

        except JIRAError as e:
            if e.status_code == 429:
                raise RateLimitError(
                    "Rate limited by JIRA. Retrying with exponential backoff..."
                ) from e
            if e.status_code == 401:
                raise AuthenticationError(
                    "Authentication failed. Check your email and API token."
                ) from e
            if e.status_code == 400:
                raise ValueError(f"Invalid JQL query: {e.text}") from e
            raise

    def get_project_names(self, project_keys: list[str]) -> dict[str, str]:
        """Fetch human-readable project names for a list of project keys.

        Returns:
            Dict mapping project key → project name. Falls back to the key
            itself if a project cannot be fetched.
        """
        client = self._get_client()
        result: dict[str, str] = {}
        for key in project_keys:
            try:
                project = client.project(key)
                result[key] = project.name
            except Exception:
                result[key] = key  # graceful fallback
        return result

    def list_link_types(self) -> list[str]:
        """Get available issue link type names from JIRA.

        Returns:
            List of link type names (e.g., ["Relates", "Blocks", "Cloners"])

        Raises:
            AuthenticationError: If authentication fails
        """
        client = self._get_client()
        try:
            link_types = client.issue_link_types()
        except JIRAError as e:
            if e.status_code == 401:
                raise AuthenticationError(
                    "Authentication failed. Check your email and API token."
                ) from e
            raise
        return [lt.name for lt in link_types]

    def _issue_to_dict(self, issue) -> dict:
        """Convert JIRA issue object to dictionary."""
        return {
            "key": issue.key,
            "fields": issue.raw.get("fields", {}),
        }
