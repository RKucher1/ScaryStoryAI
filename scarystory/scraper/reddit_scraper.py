"""Reddit story scraper using PRAW."""

import logging
import time
from typing import Any, Generator

import praw
from praw.models import Submission

logger = logging.getLogger(__name__)


class RedditScraper:
    """Scrapes stories from Reddit using the official API via PRAW."""

    def __init__(self, config: dict[str, Any]):
        reddit_config = config["reddit"]
        self.reddit = praw.Reddit(
            client_id=reddit_config["client_id"],
            client_secret=reddit_config["client_secret"],
            user_agent=reddit_config["user_agent"],
            username=reddit_config.get("username", ""),
            password=reddit_config.get("password", ""),
        )
        self.reddit.read_only = True
        self.rate_limit_delay = config.get("rate_limit", {}).get("request_delay", 2.0)
        self.max_per_subreddit = config.get("rate_limit", {}).get(
            "max_per_subreddit", 25
        )
        self.scoring_config = config.get("scoring", {})
        logger.info("Reddit scraper initialized (read-only mode)")

    def scrape_subreddit(
        self,
        subreddit_name: str,
        sort: str = "top",
        time_filter: str = "week",
        limit: int | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Scrape stories from a single subreddit.

        Args:
            subreddit_name: Name of the subreddit (without r/).
            sort: Sort method - "top", "hot", "new", "rising".
            time_filter: Time filter for "top" sort - "hour", "day", "week", "month", "year", "all".
            limit: Max number of posts to fetch. Defaults to config value.

        Yields:
            Dict with story data for each qualifying post.
        """
        limit = limit or self.max_per_subreddit
        subreddit = self.reddit.subreddit(subreddit_name)

        logger.info(
            "Scraping r/%s (sort=%s, time=%s, limit=%d)",
            subreddit_name,
            sort,
            time_filter,
            limit,
        )

        fetch_method = {
            "top": lambda: subreddit.top(time_filter=time_filter, limit=limit),
            "hot": lambda: subreddit.hot(limit=limit),
            "new": lambda: subreddit.new(limit=limit),
            "rising": lambda: subreddit.rising(limit=limit),
        }.get(sort, lambda: subreddit.top(time_filter=time_filter, limit=limit))

        count = 0
        for submission in fetch_method():
            story = self._extract_story(submission, subreddit_name)
            if story and self._passes_filters(story):
                count += 1
                yield story

            # Respect rate limits
            time.sleep(self.rate_limit_delay)

        logger.info("Scraped %d stories from r/%s", count, subreddit_name)

    def scrape_multiple_subreddits(
        self,
        subreddit_groups: dict[str, list[str]],
        sort: str = "top",
        time_filter: str = "week",
    ) -> Generator[dict[str, Any], None, None]:
        """Scrape stories from multiple subreddit groups.

        Args:
            subreddit_groups: Dict mapping group names to lists of subreddit names.
            sort: Sort method.
            time_filter: Time filter.

        Yields:
            Dict with story data.
        """
        for group_name, subreddits in subreddit_groups.items():
            logger.info("Processing subreddit group: %s", group_name)
            for sub_name in subreddits:
                try:
                    yield from self.scrape_subreddit(
                        sub_name, sort=sort, time_filter=time_filter
                    )
                except Exception:
                    logger.exception("Error scraping r/%s", sub_name)
                    continue

    def _extract_story(
        self, submission: Submission, subreddit_name: str
    ) -> dict[str, Any] | None:
        """Extract story data from a Reddit submission."""
        # Skip non-text posts
        if not submission.selftext or submission.selftext in ("[removed]", "[deleted]"):
            return None

        # Skip stickied/pinned posts (usually mod announcements)
        if submission.stickied:
            return None

        total_awards = getattr(submission, "total_awards_received", 0)

        return {
            "reddit_id": submission.id,
            "subreddit": subreddit_name,
            "title": submission.title,
            "body": submission.selftext,
            "author": str(submission.author) if submission.author else "[deleted]",
            "url": f"https://reddit.com{submission.permalink}",
            "upvotes": submission.score,
            "comments": submission.num_comments,
            "awards": total_awards,
            "post_created_utc": submission.created_utc,
            "metadata": {
                "upvote_ratio": submission.upvote_ratio,
                "is_original_content": submission.is_original_content,
                "link_flair_text": submission.link_flair_text,
            },
        }

    def _passes_filters(self, story: dict[str, Any]) -> bool:
        """Check if a story passes minimum quality filters."""
        min_upvotes = self.scoring_config.get("min_upvotes", 50)
        min_length = self.scoring_config.get("min_body_length", 500)
        max_length = self.scoring_config.get("max_body_length", 30000)

        body_length = len(story["body"])

        if story["upvotes"] < min_upvotes:
            logger.debug(
                "Filtered out (low upvotes: %d): %s",
                story["upvotes"],
                story["title"][:50],
            )
            return False

        if body_length < min_length:
            logger.debug(
                "Filtered out (too short: %d chars): %s",
                body_length,
                story["title"][:50],
            )
            return False

        if body_length > max_length:
            logger.debug(
                "Filtered out (too long: %d chars): %s",
                body_length,
                story["title"][:50],
            )
            return False

        return True
