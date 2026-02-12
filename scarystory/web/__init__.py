"""Flask web application for ScaryStoryAI dashboard."""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from flask import Flask

from scarystory.utils.config import load_config

logger = logging.getLogger(__name__)


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

    if config is None:
        config = load_config()
    app.config["STORY_CONFIG"] = config

    # Track background pipeline jobs
    app.config["PIPELINE_JOBS"] = {}
    app.config["PIPELINE_LOCK"] = threading.Lock()

    from scarystory.web.routes import register_routes

    register_routes(app)

    return app
