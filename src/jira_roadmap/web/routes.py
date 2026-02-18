"""HTTP route handlers for JIRA Roadmap web interface."""

from datetime import date, timedelta

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


@bp.route("/demo")
def demo():
    """Render the roadmap with built-in demo data (no JIRA credentials needed)."""
    today = date.today()

    def d(offset_days):
        return (today + timedelta(days=offset_days)).isoformat()

    result_json = {
        "jql_query": "type = Initiative AND project = DEMO",
        "jira_url": "https://demo.atlassian.net",
        "timeline_start": d(-60),
        "timeline_end": d(330),
        # (from, to) pairs — "from" blocks "to"
        "initiative_deps": [
            ["INIT-4", "INIT-1"],   # Legacy migration must finish before Platform Modernisation
            ["INIT-1", "INIT-3"],   # Platform Modernisation before Analytics Dashboard
        ],
        "epic_deps": [
            ["EPIC-1", "EPIC-2"],   # API Gateway migration before Service mesh rollout
            ["EPIC-2", "EPIC-3"],   # Service mesh rollout before Observability uplift
            ["EPIC-4", "EPIC-5"],   # iOS MVP before Android MVP
        ],
        "initiatives": [
            {
                "key": "INIT-1", "title": "Platform Modernisation",
                "status": "In Progress", "status_category": "indeterminate",
                "start_date": d(-45), "end_date": d(180),
                "url": "#",
                "epics": [
                    {"key": "EPIC-1", "title": "API Gateway migration",
                     "status": "In Progress", "status_category": "indeterminate",
                     "start_date": d(-45), "end_date": d(45), "url": "#",
                     "done_stories": 5, "inprogress_stories": 2, "cancelled_stories": 0,
                     "total_stories": 8},
                    {"key": "EPIC-2", "title": "Service mesh rollout",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(30), "end_date": d(120), "url": "#",
                     "done_stories": 0, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 6},
                    {"key": "EPIC-3", "title": "Observability uplift",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(90), "end_date": d(180), "url": "#",
                     "done_stories": 0, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 4},
                ],
            },
            {
                "key": "INIT-2", "title": "Mobile App Launch",
                "status": "In Progress", "status_category": "indeterminate",
                "start_date": d(-20), "end_date": d(150),
                "url": "#",
                "epics": [
                    {"key": "EPIC-4", "title": "iOS MVP",
                     "status": "In Progress", "status_category": "indeterminate",
                     "start_date": d(-20), "end_date": d(60), "url": "#",
                     "done_stories": 7, "inprogress_stories": 2, "cancelled_stories": 1,
                     "total_stories": 10},
                    {"key": "EPIC-5", "title": "Android MVP",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(50), "end_date": d(120), "url": "#",
                     "done_stories": 2, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 9},
                    {"key": "EPIC-6", "title": "Push notifications",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(100), "end_date": d(150), "url": "#",
                     "done_stories": 0, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 3},
                ],
            },
            {
                "key": "INIT-3", "title": "Analytics Dashboard",
                "status": "To Do", "status_category": "new",
                "start_date": d(60), "end_date": d(270),
                "url": "#",
                "epics": [
                    {"key": "EPIC-7", "title": "Data pipeline",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(60), "end_date": d(150), "url": "#",
                     "done_stories": 0, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 7},
                    {"key": "EPIC-8", "title": "Dashboard UI",
                     "status": "To Do", "status_category": "new",
                     "start_date": d(150), "end_date": d(270), "url": "#",
                     "done_stories": 0, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 5},
                ],
            },
            {
                "key": "INIT-4", "title": "Legacy System Migration",
                "status": "Done", "status_category": "done",
                "start_date": d(-150), "end_date": d(-10),
                "url": "#",
                "epics": [
                    {"key": "EPIC-9", "title": "Data extraction",
                     "status": "Done", "status_category": "done",
                     "start_date": d(-150), "end_date": d(-80), "url": "#",
                     "done_stories": 6, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 6},
                    {"key": "EPIC-10", "title": "Cutover & decommission",
                     "status": "Done", "status_category": "done",
                     "start_date": d(-80), "end_date": d(-10), "url": "#",
                     "done_stories": 4, "inprogress_stories": 0, "cancelled_stories": 0,
                     "total_stories": 4},
                ],
            },
            {
                # Initiative with no dates: all 3 epics are in progress but have no
                # roadmap date fields set.  Each bar should span the full timeline
                # with a fading left and right edge.
                "key": "INIT-5", "title": "Continuous Improvement",
                "status": "In Progress", "status_category": "indeterminate",
                "start_date": None, "end_date": None,
                "url": "#",
                "epics": [
                    {"key": "EPIC-11", "title": "Performance optimisation",
                     "status": "In Progress", "status_category": "indeterminate",
                     "start_date": None, "end_date": None, "url": "#",
                     "done_stories": 2, "inprogress_stories": 3, "cancelled_stories": 0,
                     "total_stories": 8},
                    {"key": "EPIC-12", "title": "Developer experience",
                     "status": "In Progress", "status_category": "indeterminate",
                     "start_date": None, "end_date": None, "url": "#",
                     "done_stories": 0, "inprogress_stories": 2, "cancelled_stories": 0,
                     "total_stories": 5},
                    {"key": "EPIC-13", "title": "Documentation refresh",
                     "status": "In Progress", "status_category": "indeterminate",
                     "start_date": None, "end_date": None, "url": "#",
                     "done_stories": 1, "inprogress_stories": 1, "cancelled_stories": 0,
                     "total_stories": 4},
                ],
            },
        ],
    }

    return render_template(
        "index.html",
        has_config=True,
        result=True,
        result_json=result_json,
        jql=result_json["jql_query"],
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
