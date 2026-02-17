"""HTTP route handlers for JIRA Roadmap web interface."""

from flask import Blueprint, jsonify, render_template, request

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
    RoadmapError,
)
from jira_roadmap.jira_client import AuthenticationError, JiraClient
from jira_roadmap.jira_client import ConnectionError as JiraClientConnectionError
from jira_roadmap.roadmap import fetch_roadmap, roadmap_result_to_dict

bp = Blueprint("main", __name__, static_folder="static", template_folder="templates")


@bp.route("/health")
def health():
    """Health check endpoint."""
    config_loaded = config_exists()
    if config_loaded:
        return jsonify({"status": "ok", "config_loaded": True})
    else:
        return jsonify({
            "status": "error",
            "config_loaded": False,
            "message": "Configuration not found",
        }), 503


@bp.route("/")
def index():
    """Render the roadmap form."""
    has_config = config_exists()
    return render_template("index.html", has_config=has_config)


@bp.route("/", methods=["POST"])
def roadmap_post():
    """Fetch roadmap data and render with results."""
    jql = request.form.get("jql", "").strip()
    link_types_str = request.form.get("link_types", "").strip()

    if not jql:
        return render_template(
            "index.html",
            has_config=config_exists(),
            error="JQL query is required.",
            jql=jql,
        ), 400

    # Parse link types
    link_types = None
    if link_types_str:
        link_types = [lt.strip() for lt in link_types_str.split(",") if lt.strip()]

    try:
        result = fetch_roadmap(jql, link_types=link_types)
    except ConfigNotFoundError as e:
        return render_template(
            "index.html", has_config=False, error=str(e), jql=jql,
        ), 503
    except (InvalidConfigError, RoadmapConfigError) as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 503
    except JiraAuthError as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 401
    except JiraRateLimitError as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 429
    except JiraConnectionError as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 503
    except InvalidJqlError as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 400
    except NoIssuesFoundError as e:
        return render_template(
            "index.html", has_config=config_exists(), warning=str(e), jql=jql,
        ), 200
    except RoadmapError as e:
        return render_template(
            "index.html", has_config=config_exists(), error=str(e), jql=jql,
        ), 500

    return render_template(
        "index.html",
        has_config=True,
        result=result,
        result_json=roadmap_result_to_dict(result),
        jql=jql,
    )


@bp.route("/api/link-types")
def api_link_types():
    """Return available JIRA issue link types as JSON."""
    if not config_exists():
        return jsonify({"error": "Configuration not found"}), 503

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        return jsonify({"error": str(e)}), 503

    try:
        client = JiraClient(config)
        link_types = client.list_link_types()
    except AuthenticationError as e:
        return jsonify({"error": str(e)}), 401
    except JiraClientConnectionError as e:
        return jsonify({"error": str(e)}), 503

    return jsonify(link_types)
