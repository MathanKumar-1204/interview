import os
from datetime import datetime
from flask import Flask, render_template
from app.config import config_by_name, Config
from app.extensions import db
from app.routes.dashboard import dashboard_bp
from app.routes.interviews import interviews_bp
from app.routes.reports import reports_bp
from app.routes.api import api_bp


def create_app(config_name: str = "development") -> Flask:
    """Application factory for AI Interview Studio."""
    app = Flask(__name__)
    
    # Load configuration
    cfg = config_by_name.get(config_name, Config)
    app.config.from_object(cfg)

    # Ensure upload and instance directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(interviews_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)

    # Custom Jinja filters
    @app.template_filter("format_dt")
    def format_dt(value, fmt="%b %d, %Y • %I:%M %p"):
        if not value:
            return "—"
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.strftime(fmt)
            except Exception:
                return value
        return value.strftime(fmt)

    @app.template_filter("status_badge_class")
    def status_badge_class(status: str) -> str:
        mapping = {
            "draft": "badge-gray",
            "prepared": "badge-blue",
            "in_progress": "badge-amber",
            "awaiting_finalization": "badge-indigo",
            "completed": "badge-emerald",
            "interrupted": "badge-orange",
            "failed": "badge-rose",
        }
        return mapping.get((status or "").lower(), "badge-gray")

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("base.html", error_title="404 - Page Not Found", error_message="The requested resource could not be found."), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        max_mb = app.config.get("MAX_CONTENT_LENGTH", 10485760) // (1024 * 1024)
        return render_template("base.html", error_title="413 - File Too Large", error_message=f"Uploaded file exceeds the maximum limit of {max_mb} MB."), 413

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("base.html", error_title="500 - Internal Server Error", error_message="An unexpected server error occurred."), 500

    # Auto-create tables in development and testing
    with app.app_context():
        db.create_all()

    return app
