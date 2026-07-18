"""
Universal Document to Excel Converter — Main Flask Application.
Optimized for Render free tier: lazy imports, minimal startup, low memory.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from flask import Flask, send_from_directory

from config import Config

# ── Logging Setup ───────────────────────────────────────────────────────────

def _setup_logging() -> None:
    """Configure application logging."""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(Config.LOG_FORMAT))
    root_logger.addHandler(console)

    # File handler with rotation
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            Config.LOG_DIR / "app.log",
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT,
        )
        file_handler.setFormatter(logging.Formatter(Config.LOG_FORMAT))
        root_logger.addHandler(file_handler)
    except (OSError, PermissionError):
        # On Render, log dir might not be writable
        pass


# ── App Factory ─────────────────────────────────────────────────────────────

def create_app() -> Flask:
    """Create and configure the Flask application."""
    _setup_logging()
    logger = logging.getLogger(__name__)

    # Ensure directories exist
    Config.ensure_directories()

    app = Flask(
        __name__,
        static_folder=None,  # We'll serve frontend manually
    )
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

    # ── Register API routes ─────────────────────────────────────────────
    from backend.routes import api
    app.register_blueprint(api)

    # ── Serve frontend ──────────────────────────────────────────────────
    frontend_dir = Config.BASE_DIR / "frontend"

    @app.route("/")
    def index():
        return send_from_directory(str(frontend_dir), "index.html")

    @app.route("/css/<path:filename>")
    def serve_css(filename):
        return send_from_directory(str(frontend_dir / "css"), filename)

    @app.route("/js/<path:filename>")
    def serve_js(filename):
        return send_from_directory(str(frontend_dir / "js"), filename)

    @app.route("/assets/<path:filename>")
    def serve_assets(filename):
        return send_from_directory(str(frontend_dir / "assets"), filename)

    # ── Error handlers ──────────────────────────────────────────────────

    @app.errorhandler(413)
    def file_too_large(e):
        max_mb = Config.MAX_CONTENT_LENGTH / (1024 * 1024)
        return {"error": f"File too large. Maximum size is {max_mb:.0f}MB"}, 413

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Internal server error: {e}")
        return {"error": "Internal server error"}, 500

    logger.info(f"{Config.APP_NAME} v{Config.APP_VERSION} initialized")
    return app


# ── Entry Point ─────────────────────────────────────────────────────────────

app = create_app()

if __name__ == "__main__":
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )
