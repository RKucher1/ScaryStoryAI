"""SQLite database for tracking scraped stories and preventing duplicates."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StoryDatabase:
    """SQLite-backed storage for scraped Reddit stories."""

    def __init__(self, db_path: str = "scarystory.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS stories (
                id TEXT PRIMARY KEY,
                reddit_id TEXT UNIQUE NOT NULL,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                author TEXT,
                url TEXT,
                upvotes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                awards INTEGER DEFAULT 0,
                post_created_utc REAL,
                scraped_at TEXT NOT NULL,
                category TEXT,
                score REAL DEFAULT 0.0,
                is_processed INTEGER DEFAULT 0,
                is_audio_generated INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS audio_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                duration_seconds REAL,
                format TEXT DEFAULT 'mp3',
                voice_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (story_id) REFERENCES stories(id)
            );

            CREATE INDEX IF NOT EXISTS idx_stories_subreddit ON stories(subreddit);
            CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category);
            CREATE INDEX IF NOT EXISTS idx_stories_score ON stories(score DESC);
            CREATE INDEX IF NOT EXISTS idx_stories_reddit_id ON stories(reddit_id);
        """)
        self.conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    def story_exists(self, reddit_id: str) -> bool:
        """Check if a story has already been scraped."""
        cursor = self.conn.execute(
            "SELECT 1 FROM stories WHERE reddit_id = ?", (reddit_id,)
        )
        return cursor.fetchone() is not None

    def insert_story(self, story: dict[str, Any]) -> str | None:
        """Insert a new story into the database. Returns story ID or None if duplicate."""
        if self.story_exists(story["reddit_id"]):
            logger.debug("Story already exists: %s", story["reddit_id"])
            return None

        import uuid

        story_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        self.conn.execute(
            """INSERT INTO stories
               (id, reddit_id, subreddit, title, body, author, url,
                upvotes, comments, awards, post_created_utc, scraped_at,
                category, score, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                story_id,
                story["reddit_id"],
                story["subreddit"],
                story["title"],
                story["body"],
                story.get("author", "[deleted]"),
                story.get("url", ""),
                story.get("upvotes", 0),
                story.get("comments", 0),
                story.get("awards", 0),
                story.get("post_created_utc", 0),
                now,
                story.get("category", "uncategorized"),
                story.get("score", 0.0),
                json.dumps(story.get("metadata", {})),
            ),
        )
        self.conn.commit()
        logger.info("Stored story: %s (id=%s)", story["title"][:60], story_id)
        return story_id

    def mark_processed(self, story_id: str) -> None:
        """Mark a story as text-processed."""
        self.conn.execute(
            "UPDATE stories SET is_processed = 1 WHERE id = ?", (story_id,)
        )
        self.conn.commit()

    def mark_audio_generated(self, story_id: str) -> None:
        """Mark a story as having audio generated."""
        self.conn.execute(
            "UPDATE stories SET is_audio_generated = 1 WHERE id = ?", (story_id,)
        )
        self.conn.commit()

    def insert_audio_record(
        self,
        story_id: str,
        file_path: str,
        duration: float,
        fmt: str = "mp3",
        voice_id: str = "",
    ) -> None:
        """Record an audio file generation."""
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO audio_files (story_id, file_path, duration_seconds, format, voice_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (story_id, file_path, duration, fmt, voice_id, now),
        )
        self.conn.commit()

    def get_unprocessed_stories(self, limit: int = 50) -> list[dict]:
        """Get stories that haven't been text-processed yet."""
        cursor = self.conn.execute(
            """SELECT * FROM stories
               WHERE is_processed = 0
               ORDER BY score DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_stories_without_audio(self, limit: int = 50) -> list[dict]:
        """Get processed stories that don't have audio yet."""
        cursor = self.conn.execute(
            """SELECT * FROM stories
               WHERE is_processed = 1 AND is_audio_generated = 0
               ORDER BY score DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_top_stories(
        self, category: str | None = None, limit: int = 20
    ) -> list[dict]:
        """Get top-scoring stories, optionally filtered by category."""
        if category:
            cursor = self.conn.execute(
                """SELECT * FROM stories
                   WHERE category = ?
                   ORDER BY score DESC LIMIT ?""",
                (category, limit),
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM stories ORDER BY score DESC LIMIT ?", (limit,)
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(is_processed) as processed,
                SUM(is_audio_generated) as audio_generated,
                COUNT(DISTINCT subreddit) as subreddits,
                COUNT(DISTINCT category) as categories
               FROM stories"""
        )
        row = cursor.fetchone()
        return dict(row) if row else {}

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
