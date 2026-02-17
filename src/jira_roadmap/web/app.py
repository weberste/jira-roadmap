"""Flask application factory for JIRA Roadmap web interface."""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app.config["SECRET_KEY"] = "jira-roadmap-local-dev"

    from jira_roadmap.web.routes import bp
    app.register_blueprint(bp)

    return app
