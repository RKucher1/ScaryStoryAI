"""Route handlers for the ScaryStoryAI web dashboard."""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from scarystory.database.store import StoryDatabase
from scarystory.utils.config import load_config

logger = logging.getLogger(__name__)


def _get_db(app: Flask) -> StoryDatabase:
    config = app.config["STORY_CONFIG"]
    db_path = config.get("database", {}).get("path", "scarystory.db")
    return StoryDatabase(db_path)


def register_routes(app: Flask) -> None:
    """Register all route handlers."""

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @app.route("/")
    def dashboard():
        with _get_db(app) as db:
            stats = db.get_stats()
            recent = db.get_top_stories(limit=5)

        # Summarise active jobs
        jobs = app.config["PIPELINE_JOBS"]
        active_jobs = {k: v for k, v in jobs.items() if v["status"] == "running"}

        return render_template(
            "dashboard.html",
            stats=stats,
            recent_stories=recent,
            active_jobs=active_jobs,
        )

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------
    @app.route("/stories")
    def stories():
        category = request.args.get("category")
        limit = request.args.get("limit", 50, type=int)

        with _get_db(app) as db:
            story_list = db.get_top_stories(category=category, limit=limit)
            stats = db.get_stats()

        # Get distinct categories for the filter dropdown
        categories = sorted({s["category"] for s in story_list if s.get("category")})

        return render_template(
            "stories.html",
            stories=story_list,
            categories=categories,
            selected_category=category,
            stats=stats,
        )

    @app.route("/stories/<story_id>")
    def story_detail(story_id: str):
        with _get_db(app) as db:
            rows = db.get_top_stories(limit=1000)
            story = next((s for s in rows if s["id"] == story_id), None)

        if not story:
            flash("Story not found.", "error")
            return redirect(url_for("stories"))

        # Load metadata if available
        config = app.config["STORY_CONFIG"]
        output_base = Path(config.get("output", {}).get("base_dir", "output"))
        category = story.get("category", "uncategorized")

        if config.get("output", {}).get("organize_by_category", True):
            story_dir = output_base / category / story_id
        else:
            story_dir = output_base / story_id

        metadata = {}
        transcript = ""
        audio_files = []

        metadata_path = story_dir / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())

        transcript_path = story_dir / "transcript.txt"
        if transcript_path.exists():
            transcript = transcript_path.read_text()

        # Find audio files
        audio_dir = story_dir / "audio"
        if audio_dir.exists():
            audio_files = sorted(audio_dir.glob("*.mp3")) + sorted(
                audio_dir.glob("*.wav")
            )

        combined_audio = story_dir / f"full_story.{config.get('tts', {}).get('output_format', 'mp3')}"
        has_combined = combined_audio.exists()

        return render_template(
            "story_detail.html",
            story=story,
            metadata=metadata,
            transcript=transcript,
            audio_files=audio_files,
            has_combined=has_combined,
            combined_audio_name=combined_audio.name if has_combined else None,
            story_dir=str(story_dir),
        )

    @app.route("/audio/<path:filepath>")
    def serve_audio(filepath: str):
        """Serve audio files from the output directory."""
        full_path = Path(filepath)
        if not full_path.exists():
            # Try relative to output dir
            config = app.config["STORY_CONFIG"]
            output_base = Path(config.get("output", {}).get("base_dir", "output"))
            full_path = output_base / filepath

        if full_path.exists() and full_path.suffix in (".mp3", ".wav"):
            return send_file(str(full_path.resolve()))

        return "Audio file not found", 404

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    @app.route("/settings", methods=["GET"])
    def settings():
        config = app.config["STORY_CONFIG"]
        # Mask sensitive values for display
        display_config = _mask_sensitive(config)

        env_vars = {
            "REDDIT_CLIENT_ID": os.environ.get("REDDIT_CLIENT_ID", ""),
            "REDDIT_CLIENT_SECRET": _mask(os.environ.get("REDDIT_CLIENT_SECRET", "")),
            "REDDIT_USERNAME": os.environ.get("REDDIT_USERNAME", ""),
            "ELEVENLABS_API_KEY": _mask(os.environ.get("ELEVENLABS_API_KEY", "")),
        }

        return render_template(
            "settings.html",
            config=display_config,
            env_vars=env_vars,
            raw_config=config,
        )

    @app.route("/settings/env", methods=["POST"])
    def update_env():
        """Update environment variables for credentials."""
        env_map = {
            "reddit_client_id": "REDDIT_CLIENT_ID",
            "reddit_client_secret": "REDDIT_CLIENT_SECRET",
            "reddit_username": "REDDIT_USERNAME",
            "elevenlabs_api_key": "ELEVENLABS_API_KEY",
        }

        updated = []
        for form_key, env_key in env_map.items():
            value = request.form.get(form_key, "").strip()
            if value and not value.startswith("***"):
                os.environ[env_key] = value
                updated.append(env_key)

        if updated:
            # Reload config with new env vars
            app.config["STORY_CONFIG"] = load_config()
            flash(f"Updated: {', '.join(updated)}", "success")
        else:
            flash("No changes made.", "info")

        return redirect(url_for("settings"))

    @app.route("/settings/tts", methods=["POST"])
    def update_tts():
        """Update TTS provider settings."""
        config = app.config["STORY_CONFIG"]

        provider = request.form.get("tts_provider", "coqui")
        speaker = request.form.get("coqui_speaker", "p273")

        config.setdefault("tts", {})["provider"] = provider
        config.setdefault("tts", {}).setdefault("coqui", {})["speaker"] = speaker

        app.config["STORY_CONFIG"] = config
        flash(f"TTS updated: provider={provider}, speaker={speaker}", "success")
        return redirect(url_for("settings"))

    # ------------------------------------------------------------------
    # Pipeline Controls
    # ------------------------------------------------------------------
    @app.route("/pipeline")
    def pipeline():
        jobs = app.config["PIPELINE_JOBS"]
        return render_template("pipeline.html", jobs=jobs)

    @app.route("/pipeline/run", methods=["POST"])
    def pipeline_run():
        """Trigger a pipeline job in a background thread."""
        action = request.form.get("action", "run")

        valid_actions = {"scrape", "process", "audio", "run"}
        if action not in valid_actions:
            flash(f"Unknown action: {action}", "error")
            return redirect(url_for("pipeline"))

        with app.config["PIPELINE_LOCK"]:
            jobs = app.config["PIPELINE_JOBS"]
            # Don't allow duplicate running jobs
            if any(j["status"] == "running" for j in jobs.values()):
                flash("A pipeline job is already running.", "warning")
                return redirect(url_for("pipeline"))

            job_id = f"{action}_{int(time.time())}"
            jobs[job_id] = {
                "action": action,
                "status": "running",
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "result": None,
            }

        thread = threading.Thread(
            target=_run_pipeline_job,
            args=(app, job_id, action),
            daemon=True,
        )
        thread.start()

        flash(f"Pipeline '{action}' started.", "success")
        return redirect(url_for("pipeline"))

    @app.route("/pipeline/status")
    def pipeline_status():
        """JSON endpoint for job status polling."""
        jobs = app.config["PIPELINE_JOBS"]
        return jsonify(jobs)


def _run_pipeline_job(app: Flask, job_id: str, action: str) -> None:
    """Execute a pipeline action in a background thread."""
    from scarystory.processor.pipeline import StoryPipeline

    with app.app_context():
        config = app.config["STORY_CONFIG"]
        jobs = app.config["PIPELINE_JOBS"]

        try:
            with StoryPipeline(config) as pipeline:
                if action == "scrape":
                    result = pipeline.run_scrape()
                    summary = f"Scraped {len(result)} new stories"
                elif action == "process":
                    result = pipeline.run_process()
                    summary = f"Processed {len(result)} stories"
                elif action == "audio":
                    result = pipeline.run_generate_audio()
                    summary = f"Generated audio for {len(result)} stories"
                elif action == "run":
                    result = pipeline.run_full_pipeline()
                    summary = (
                        f"Scraped {result['new_stories_scraped']}, "
                        f"processed {result['stories_processed']}, "
                        f"audio for {result['audio_generated']}"
                    )
                else:
                    summary = "Unknown action"

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = summary
        except Exception as e:
            logger.exception("Pipeline job %s failed", job_id)
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["result"] = str(e)


def _mask(value: str) -> str:
    """Mask a sensitive string, showing only last 4 chars."""
    if not value or len(value) <= 4:
        return "***" if value else ""
    return "***" + value[-4:]


def _mask_sensitive(config: dict) -> dict:
    """Return a copy of config with sensitive values masked."""
    import copy

    c = copy.deepcopy(config)

    # Mask Reddit secrets
    reddit = c.get("reddit", {})
    if reddit.get("client_secret"):
        reddit["client_secret"] = _mask(reddit["client_secret"])
    if reddit.get("password"):
        reddit["password"] = _mask(reddit["password"])

    # Mask ElevenLabs key
    el = c.get("tts", {}).get("elevenlabs", {})
    if el.get("api_key"):
        el["api_key"] = _mask(el["api_key"])

    return c
