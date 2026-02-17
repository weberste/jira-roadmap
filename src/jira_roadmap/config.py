"""Configuration management for JIRA Roadmap."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import tomli_w


@dataclass
class Config:
    """Configuration for JIRA connection and roadmap settings."""

    jira_url: str
    jira_email: str
    jira_api_token: str
    start_date_field: str | None = None
    end_date_field: str | None = None

    def validate(self) -> list[str]:
        """Validate configuration values. Returns list of error messages."""
        errors: list[str] = []

        if not self.jira_url:
            errors.append("JIRA URL is required")
        else:
            parsed = urlparse(self.jira_url)
            if parsed.scheme not in ("http", "https"):
                errors.append("JIRA URL must start with http:// or https://")
            if not parsed.netloc:
                errors.append("JIRA URL must include a domain")

        if not self.jira_email:
            errors.append("JIRA email is required")
        elif "@" not in self.jira_email:
            errors.append("JIRA email must be a valid email address")

        if not self.jira_api_token:
            errors.append("JIRA API token is required")

        return errors


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    return Path.home() / ".jira-roadmap"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"


def config_exists() -> bool:
    """Check if configuration file exists."""
    return get_config_path().exists()


def load_config() -> Config:
    """Load configuration from TOML file.

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_path = get_config_path()

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration not found at {config_path}. "
            "Create ~/.jira-roadmap/config.toml to set up."
        )

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    jira_section = data.get("jira", {})
    roadmap_section = data.get("roadmap", {})

    config = Config(
        jira_url=jira_section.get("url", ""),
        jira_email=jira_section.get("email", ""),
        jira_api_token=jira_section.get("api_token", ""),
        start_date_field=roadmap_section.get("start_date_field"),
        end_date_field=roadmap_section.get("end_date_field"),
    )

    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid configuration: {'; '.join(errors)}")

    return config


def save_config(config: Config) -> None:
    """Save configuration to TOML file."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()

    data: dict = {
        "jira": {
            "url": config.jira_url,
            "email": config.jira_email,
            "api_token": config.jira_api_token,
        },
    }

    if config.start_date_field or config.end_date_field:
        roadmap_data: dict[str, str] = {}
        if config.start_date_field:
            roadmap_data["start_date_field"] = config.start_date_field
        if config.end_date_field:
            roadmap_data["end_date_field"] = config.end_date_field
        data["roadmap"] = roadmap_data

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)
