"""Tests for the Flask web dashboard."""

import pytest

from scarystory.web import create_app


@pytest.fixture
def app(tmp_path):
    config = {
        "reddit": {
            "client_id": "test",
            "client_secret": "test",
            "user_agent": "test",
        },
        "database": {"path": str(tmp_path / "test.db")},
        "output": {"base_dir": str(tmp_path / "output"), "organize_by_category": True},
        "tts": {"provider": "coqui", "coqui": {"speaker": "p273"}, "output_format": "mp3"},
        "scoring": {},
        "categories": {},
        "processing": {"chunk_pause": 1.0},
        "rate_limit": {"request_delay": 2.0, "max_per_subreddit": 25, "max_per_run": 100},
    }
    app = create_app(config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestDashboard:
    def test_dashboard_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_dashboard_shows_stats(self, client):
        resp = client.get("/")
        assert b"Total Stories" in resp.data


class TestStories:
    def test_stories_page_loads(self, client):
        resp = client.get("/stories")
        assert resp.status_code == 200
        assert b"Stories" in resp.data

    def test_stories_with_category_filter(self, client):
        resp = client.get("/stories?category=stranger_danger")
        assert resp.status_code == 200


class TestSettings:
    def test_settings_page_loads(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert b"API Credentials" in resp.data
        assert b"Text-to-Speech" in resp.data

    def test_update_tts_settings(self, client):
        resp = client.post(
            "/settings/tts",
            data={"tts_provider": "coqui", "coqui_speaker": "p317"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"TTS updated" in resp.data


class TestPipeline:
    def test_pipeline_page_loads(self, client):
        resp = client.get("/pipeline")
        assert resp.status_code == 200
        assert b"Pipeline Controls" in resp.data

    def test_pipeline_status_json(self, client):
        resp = client.get("/pipeline/status")
        assert resp.status_code == 200
        assert resp.content_type == "application/json"


class TestAudio:
    def test_missing_audio_returns_404(self, client):
        resp = client.get("/audio/nonexistent.mp3")
        assert resp.status_code == 404
