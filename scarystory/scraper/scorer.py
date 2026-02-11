"""Story scoring and ranking engine."""

import logging
import math
import time
from typing import Any

logger = logging.getLogger(__name__)


class StoryScorer:
    """Scores and ranks stories based on engagement metrics and content analysis."""

    def __init__(self, config: dict[str, Any]):
        self.scoring = config.get("scoring", {})
        self.categories = config.get("categories", {})

        # Scoring weights
        self.upvote_weight = self.scoring.get("upvote_weight", 1.0)
        self.comment_weight = self.scoring.get("comment_weight", 1.5)
        self.award_weight = self.scoring.get("award_weight", 2.0)
        self.category_match_bonus = self.scoring.get("category_match_bonus", 10.0)
        self.ai_penalty = self.scoring.get("ai_penalty", -50.0)
        self.freshness_days = self.scoring.get("freshness_days", 7)
        self.freshness_bonus = self.scoring.get("freshness_bonus", 5.0)

    def score_story(self, story: dict[str, Any]) -> dict[str, Any]:
        """Score a story and assign it to a category. Returns the story with score and category added."""
        engagement_score = self._engagement_score(story)
        category, category_score = self._categorize(story)
        freshness_score = self._freshness_score(story)
        authenticity_score = self._authenticity_score(story)

        total_score = (
            engagement_score + category_score + freshness_score + authenticity_score
        )

        story["score"] = round(total_score, 2)
        story["category"] = category

        logger.debug(
            "Scored story '%s': total=%.1f (engagement=%.1f, category=%.1f, "
            "freshness=%.1f, authenticity=%.1f) -> %s",
            story["title"][:40],
            total_score,
            engagement_score,
            category_score,
            freshness_score,
            authenticity_score,
            category,
        )

        return story

    def _engagement_score(self, story: dict[str, Any]) -> float:
        """Score based on engagement metrics (log-scaled)."""
        upvotes = max(story.get("upvotes", 0), 1)
        comments = max(story.get("comments", 0), 1)
        awards = max(story.get("awards", 0), 0)

        score = (
            math.log10(upvotes) * self.upvote_weight
            + math.log10(comments) * self.comment_weight
            + awards * self.award_weight
        )
        return score

    def _categorize(self, story: dict[str, Any]) -> tuple[str, float]:
        """Categorize a story and return (category_name, bonus_score)."""
        text = (story.get("title", "") + " " + story.get("body", "")).lower()

        best_category = "uncategorized"
        best_score = 0.0

        for cat_name, cat_config in self.categories.items():
            keywords = cat_config.get("keywords", [])
            weight = cat_config.get("weight", 1.0)

            match_count = sum(1 for kw in keywords if kw.lower() in text)
            if match_count > 0:
                cat_score = match_count * self.category_match_bonus * weight
                if cat_score > best_score:
                    best_score = cat_score
                    best_category = cat_name

        return best_category, best_score

    def _freshness_score(self, story: dict[str, Any]) -> float:
        """Bonus score for recent stories."""
        created_utc = story.get("post_created_utc", 0)
        if not created_utc:
            return 0.0

        age_days = (time.time() - created_utc) / 86400
        if age_days < self.freshness_days:
            # Linear decay within freshness window
            return self.freshness_bonus * (1 - age_days / self.freshness_days)
        return 0.0

    def _authenticity_score(self, story: dict[str, Any]) -> float:
        """Heuristic score for story authenticity. Penalizes likely AI-generated content."""
        body = story.get("body", "")
        penalty = 0.0

        # AI-generated content indicators
        ai_phrases = [
            "as an ai",
            "i cannot",
            "it's important to note",
            "in conclusion",
            "it is worth mentioning",
            "from that day forward",
            "little did i know",
            "to this day, i still",
            "i'll never forget the look",
        ]

        body_lower = body.lower()
        ai_hits = sum(1 for phrase in ai_phrases if phrase in body_lower)
        if ai_hits >= 3:
            penalty += self.ai_penalty
            logger.debug(
                "AI penalty applied (%d indicators): %s",
                ai_hits,
                story["title"][:40],
            )

        # Overly formulaic structure detection
        # Stories with extremely uniform paragraph lengths may be AI-generated
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        if len(paragraphs) >= 5:
            lengths = [len(p) for p in paragraphs]
            avg_len = sum(lengths) / len(lengths) if lengths else 0
            if avg_len > 0:
                variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
                # Very low variance in paragraph lengths is suspicious
                cv = (variance**0.5) / avg_len
                if cv < 0.15:
                    penalty += self.ai_penalty * 0.5

        # Authenticity bonus: first-person narrative with specific details
        authenticity_markers = [
            "i remember",
            "my friend",
            "my mom",
            "my dad",
            "my sister",
            "my brother",
            "years ago",
            "when i was",
            "i was about",
            "i lived",
            "our neighborhood",
            "my house",
        ]
        auth_hits = sum(1 for marker in authenticity_markers if marker in body_lower)
        bonus = min(auth_hits * 2.0, 10.0)

        return penalty + bonus

    def rank_stories(self, stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score and rank a list of stories by their total score."""
        scored = [self.score_story(s) for s in stories]
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored
