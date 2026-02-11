"""Content safety filter to avoid inappropriate or harmful content."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Terms that indicate content unsuitable for narration
BLOCKED_PATTERNS = [
    # Explicit sexual content
    r"\b(?:nsfw|explicit sexual|graphic sex)\b",
    # Detailed self-harm instructions
    r"\b(?:how to (?:harm|hurt|kill) yourself)\b",
    # Doxxing / personal information
    r"\b(?:their (?:real )?(?:phone number|home address|social security))\b",
]

# Flair tags that indicate unsuitable content
BLOCKED_FLAIRS = {
    "nsfw",
    "trigger warning: sa",
    "tw: sexual assault",
    "meta",
    "mod post",
}


class ContentFilter:
    """Filters out stories with inappropriate or harmful content."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]
        self.blocked_flairs = BLOCKED_FLAIRS

    def is_safe(self, story: dict[str, Any]) -> bool:
        """Check if a story passes content safety filters.

        Returns True if the story is safe to use, False if it should be skipped.
        """
        # Check flair
        flair = (story.get("metadata", {}).get("link_flair_text") or "").lower()
        if flair in self.blocked_flairs:
            logger.info(
                "Content filtered (blocked flair '%s'): %s",
                flair,
                story.get("title", "")[:50],
            )
            return False

        # Check title + body against blocked patterns
        text = story.get("title", "") + " " + story.get("body", "")
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                logger.info(
                    "Content filtered (blocked pattern): %s",
                    story.get("title", "")[:50],
                )
                return False

        return True
