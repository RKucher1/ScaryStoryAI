"""Tests for the story scorer module."""

import time

import pytest

from scarystory.scraper.scorer import StoryScorer

DEFAULT_CONFIG = {
    "scoring": {
        "min_upvotes": 50,
        "min_body_length": 500,
        "max_body_length": 30000,
        "upvote_weight": 1.0,
        "comment_weight": 1.5,
        "award_weight": 2.0,
        "category_match_bonus": 10.0,
        "ai_penalty": -50.0,
        "freshness_days": 7,
        "freshness_bonus": 5.0,
    },
    "categories": {
        "stranger_danger": {
            "keywords": ["stranger", "followed me", "stalker"],
            "weight": 1.8,
        },
        "workplace_horror": {
            "keywords": ["work", "coworker", "night shift"],
            "weight": 1.3,
        },
    },
}


@pytest.fixture
def scorer():
    return StoryScorer(DEFAULT_CONFIG)


def _make_story(**overrides):
    base = {
        "reddit_id": "test123",
        "subreddit": "nosleep",
        "title": "A scary story",
        "body": "This is the body of the story. " * 50,
        "upvotes": 500,
        "comments": 100,
        "awards": 2,
        "post_created_utc": time.time() - 86400,  # 1 day ago
    }
    base.update(overrides)
    return base


class TestScoring:
    def test_score_is_positive_for_good_story(self, scorer):
        story = _make_story(upvotes=1000, comments=200, awards=5)
        scored = scorer.score_story(story)
        assert scored["score"] > 0

    def test_higher_engagement_higher_score(self, scorer):
        low = scorer.score_story(_make_story(upvotes=100, comments=10, awards=0))
        high = scorer.score_story(_make_story(upvotes=5000, comments=500, awards=10))
        assert high["score"] > low["score"]

    def test_category_assignment(self, scorer):
        story = _make_story(
            body="A stranger followed me home from work. The stalker was relentless."
        )
        scored = scorer.score_story(story)
        assert scored["category"] == "stranger_danger"

    def test_uncategorized_when_no_match(self, scorer):
        story = _make_story(body="Just a generic tale about nothing specific.")
        scored = scorer.score_story(story)
        assert scored["category"] == "uncategorized"

    def test_freshness_bonus_for_recent_story(self, scorer):
        recent = scorer.score_story(
            _make_story(post_created_utc=time.time() - 3600)  # 1 hour ago
        )
        old = scorer.score_story(
            _make_story(post_created_utc=time.time() - 30 * 86400)  # 30 days ago
        )
        assert recent["score"] > old["score"]


class TestAuthenticity:
    def test_ai_penalty_for_formulaic_content(self, scorer):
        ai_text = (
            "It's important to note that from that day forward, "
            "little did I know that in conclusion, "
            "as an ai I cannot help but mention "
        ) * 10
        story = _make_story(body=ai_text)
        scored = scorer.score_story(story)
        # Score should be lower due to AI penalty
        normal = scorer.score_story(_make_story())
        assert scored["score"] < normal["score"]

    def test_authenticity_bonus_for_personal_details(self, scorer):
        personal = _make_story(
            body="I remember when I was about 12, my friend and I "
            "lived in our neighborhood near the woods. My mom always "
            "warned us. Years ago this happened."
        )
        generic = _make_story(body="A thing happened somewhere to someone.")
        scored_personal = scorer.score_story(personal)
        scored_generic = scorer.score_story(generic)
        assert scored_personal["score"] > scored_generic["score"]


class TestRanking:
    def test_rank_stories_returns_sorted(self, scorer):
        stories = [
            _make_story(upvotes=100, comments=10),
            _make_story(upvotes=5000, comments=500, awards=10),
            _make_story(upvotes=1000, comments=100),
        ]
        ranked = scorer.rank_stories(stories)
        scores = [s["score"] for s in ranked]
        assert scores == sorted(scores, reverse=True)
