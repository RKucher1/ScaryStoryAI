"""Tests for the content safety filter."""

import pytest

from scarystory.processor.content_filter import ContentFilter


@pytest.fixture
def content_filter():
    return ContentFilter()


def _make_story(**overrides):
    base = {
        "title": "A Scary Story",
        "body": "Something creepy happened to me last year.",
        "metadata": {"link_flair_text": None},
    }
    base.update(overrides)
    return base


class TestContentFilter:
    def test_normal_story_passes(self, content_filter):
        story = _make_story()
        assert content_filter.is_safe(story) is True

    def test_nsfw_flair_blocked(self, content_filter):
        story = _make_story(metadata={"link_flair_text": "NSFW"})
        assert content_filter.is_safe(story) is False

    def test_meta_flair_blocked(self, content_filter):
        story = _make_story(metadata={"link_flair_text": "Meta"})
        assert content_filter.is_safe(story) is False

    def test_blocked_pattern_in_body(self, content_filter):
        story = _make_story(body="This story contains NSFW explicit sexual content.")
        assert content_filter.is_safe(story) is False

    def test_missing_metadata_still_works(self, content_filter):
        story = {"title": "Test", "body": "Normal story."}
        assert content_filter.is_safe(story) is True

    def test_none_flair_passes(self, content_filter):
        story = _make_story(metadata={"link_flair_text": None})
        assert content_filter.is_safe(story) is True
