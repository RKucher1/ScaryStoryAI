"""Tests for the database module."""

import os
import tempfile
import time

import pytest

from scarystory.database.store import StoryDatabase


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = StoryDatabase(path)
    yield database
    database.close()
    os.unlink(path)


def _make_story(reddit_id="abc123", **overrides):
    base = {
        "reddit_id": reddit_id,
        "subreddit": "nosleep",
        "title": "Test Story",
        "body": "Body text " * 100,
        "author": "testuser",
        "url": "https://reddit.com/r/nosleep/comments/abc123",
        "upvotes": 500,
        "comments": 50,
        "awards": 2,
        "post_created_utc": time.time(),
        "category": "stranger_danger",
        "score": 25.5,
    }
    base.update(overrides)
    return base


class TestInsertAndQuery:
    def test_insert_story(self, db):
        story_id = db.insert_story(_make_story())
        assert story_id is not None

    def test_duplicate_returns_none(self, db):
        db.insert_story(_make_story(reddit_id="dup1"))
        result = db.insert_story(_make_story(reddit_id="dup1"))
        assert result is None

    def test_story_exists(self, db):
        db.insert_story(_make_story(reddit_id="exists1"))
        assert db.story_exists("exists1")
        assert not db.story_exists("nonexistent")

    def test_get_unprocessed(self, db):
        db.insert_story(_make_story(reddit_id="unproc1"))
        db.insert_story(_make_story(reddit_id="unproc2"))
        stories = db.get_unprocessed_stories()
        assert len(stories) == 2

    def test_mark_processed(self, db):
        story_id = db.insert_story(_make_story(reddit_id="proc1"))
        db.mark_processed(story_id)
        unprocessed = db.get_unprocessed_stories()
        assert len(unprocessed) == 0

    def test_get_stories_without_audio(self, db):
        story_id = db.insert_story(_make_story(reddit_id="audio1"))
        db.mark_processed(story_id)
        stories = db.get_stories_without_audio()
        assert len(stories) == 1

    def test_mark_audio_generated(self, db):
        story_id = db.insert_story(_make_story(reddit_id="audio2"))
        db.mark_processed(story_id)
        db.mark_audio_generated(story_id)
        stories = db.get_stories_without_audio()
        assert len(stories) == 0

    def test_get_top_stories_by_category(self, db):
        db.insert_story(
            _make_story(reddit_id="cat1", category="horror", score=10.0)
        )
        db.insert_story(
            _make_story(reddit_id="cat2", category="horror", score=20.0)
        )
        db.insert_story(
            _make_story(reddit_id="cat3", category="comedy", score=30.0)
        )
        horror = db.get_top_stories(category="horror")
        assert len(horror) == 2
        assert horror[0]["score"] > horror[1]["score"]


class TestAudioRecords:
    def test_insert_audio_record(self, db):
        story_id = db.insert_story(_make_story(reddit_id="ar1"))
        db.insert_audio_record(
            story_id=story_id,
            file_path="/output/test.mp3",
            duration=120.5,
            fmt="mp3",
            voice_id="voice1",
        )
        # No exception means success


class TestStats:
    def test_stats_empty_db(self, db):
        stats = db.get_stats()
        assert stats["total"] == 0

    def test_stats_with_data(self, db):
        story_id = db.insert_story(_make_story(reddit_id="s1"))
        db.mark_processed(story_id)
        db.insert_story(_make_story(reddit_id="s2", subreddit="creepyencounters"))
        stats = db.get_stats()
        assert stats["total"] == 2
        assert stats["processed"] == 1
        assert stats["subreddits"] == 2


class TestContextManager:
    def test_context_manager(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with StoryDatabase(path) as db:
                db.insert_story(_make_story())
        finally:
            os.unlink(path)
