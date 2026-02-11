"""Story processing pipeline - orchestrates scraping through audio generation."""

import json
import logging
from pathlib import Path
from typing import Any

from scarystory.database.store import StoryDatabase
from scarystory.processor.text_cleaner import TextCleaner
from scarystory.scraper.reddit_scraper import RedditScraper
from scarystory.scraper.scorer import StoryScorer
from scarystory.tts.engine import TTSEngine

logger = logging.getLogger(__name__)


class StoryPipeline:
    """End-to-end pipeline for scraping, processing, and converting stories."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.db = StoryDatabase(config.get("database", {}).get("path", "scarystory.db"))
        self.scraper = RedditScraper(config)
        self.scorer = StoryScorer(config)
        self.cleaner = TextCleaner(config)
        self.tts = TTSEngine(config)

        output_config = config.get("output", {})
        self.output_base = Path(output_config.get("base_dir", "output"))
        self.organize_by_category = output_config.get("organize_by_category", True)

        self.max_per_run = config.get("rate_limit", {}).get("max_per_run", 100)

    def run_scrape(
        self,
        sort: str = "top",
        time_filter: str = "week",
        subreddit_groups: dict[str, list[str]] | None = None,
    ) -> list[dict]:
        """Scrape stories from Reddit and store them in the database.

        Returns list of newly stored stories.
        """
        groups = subreddit_groups or self.config.get("subreddits", {})
        new_stories = []
        total_scraped = 0

        for story in self.scraper.scrape_multiple_subreddits(
            groups, sort=sort, time_filter=time_filter
        ):
            if total_scraped >= self.max_per_run:
                logger.info("Reached max stories per run (%d)", self.max_per_run)
                break

            # Score and categorize
            story = self.scorer.score_story(story)

            # Store in database (skips duplicates)
            story_id = self.db.insert_story(story)
            if story_id:
                story["id"] = story_id
                new_stories.append(story)
                total_scraped += 1

        logger.info(
            "Scrape complete: %d new stories stored (of %d total processed)",
            len(new_stories),
            total_scraped,
        )
        return new_stories

    def run_process(self, limit: int = 50) -> list[dict]:
        """Process unprocessed stories (clean text, generate transcripts).

        Returns list of processed stories with their output paths.
        """
        stories = self.db.get_unprocessed_stories(limit=limit)
        if not stories:
            logger.info("No unprocessed stories found")
            return []

        processed = []
        for story in stories:
            try:
                result = self._process_single_story(story)
                processed.append(result)
                self.db.mark_processed(story["id"])
            except Exception:
                logger.exception(
                    "Failed to process story: %s", story["title"][:50]
                )
                continue

        logger.info("Processed %d stories", len(processed))
        return processed

    def run_generate_audio(self, limit: int = 50) -> list[dict]:
        """Generate audio for processed stories without audio.

        Returns list of generation results.
        """
        stories = self.db.get_stories_without_audio(limit=limit)
        if not stories:
            logger.info("No stories pending audio generation")
            return []

        results = []
        for story in stories:
            try:
                result = self._generate_audio_for_story(story)
                results.append(result)
                self.db.mark_audio_generated(story["id"])
            except Exception:
                logger.exception(
                    "Failed to generate audio: %s", story["title"][:50]
                )
                continue

        logger.info("Generated audio for %d stories", len(results))
        return results

    def run_full_pipeline(
        self,
        sort: str = "top",
        time_filter: str = "week",
    ) -> dict[str, Any]:
        """Run the complete pipeline: scrape -> process -> generate audio."""
        logger.info("Starting full pipeline run")

        new_stories = self.run_scrape(sort=sort, time_filter=time_filter)
        processed = self.run_process()
        audio_results = self.run_generate_audio()

        stats = self.db.get_stats()

        result = {
            "new_stories_scraped": len(new_stories),
            "stories_processed": len(processed),
            "audio_generated": len(audio_results),
            "database_stats": stats,
        }

        logger.info("Pipeline complete: %s", result)
        return result

    def _process_single_story(self, story: dict) -> dict:
        """Process a single story: clean text, chunk, save transcript."""
        category = story.get("category", "uncategorized")
        story_dir = self._get_story_dir(story["id"], category)
        story_dir.mkdir(parents=True, exist_ok=True)

        # Clean the story text
        cleaned_text = self.cleaner.clean(story["body"])

        # Chunk for TTS
        chunks = self.cleaner.chunk_text(cleaned_text)

        # Save transcript
        transcript_path = story_dir / "transcript.txt"
        transcript_path.write_text(cleaned_text)

        # Save chunks
        chunks_dir = story_dir / "chunks"
        chunks_dir.mkdir(exist_ok=True)
        for i, chunk in enumerate(chunks):
            (chunks_dir / f"chunk_{i:03d}.txt").write_text(chunk)

        # Save metadata
        metadata = {
            "story_id": story["id"],
            "title": story["title"],
            "subreddit": story["subreddit"],
            "author": story.get("author", "[deleted]"),
            "url": story.get("url", ""),
            "category": category,
            "score": story.get("score", 0),
            "upvotes": story.get("upvotes", 0),
            "comments": story.get("comments", 0),
            "awards": story.get("awards", 0),
            "word_count": len(cleaned_text.split()),
            "chunk_count": len(chunks),
            "original_length": len(story["body"]),
            "cleaned_length": len(cleaned_text),
        }
        metadata_path = story_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))

        logger.info(
            "Processed: '%s' -> %d chunks, %d words",
            story["title"][:40],
            len(chunks),
            metadata["word_count"],
        )

        return {
            "story_id": story["id"],
            "transcript_path": str(transcript_path),
            "metadata_path": str(metadata_path),
            "chunks": len(chunks),
            "word_count": metadata["word_count"],
        }

    def _generate_audio_for_story(self, story: dict) -> dict:
        """Generate audio files for a processed story."""
        category = story.get("category", "uncategorized")
        story_dir = self._get_story_dir(story["id"], category)

        # Read chunks
        chunks_dir = story_dir / "chunks"
        if not chunks_dir.exists():
            raise FileNotFoundError(
                f"Chunks not found for story {story['id']}. Run processing first."
            )

        chunk_files = sorted(chunks_dir.glob("chunk_*.txt"))
        chunks = [f.read_text() for f in chunk_files]

        if not chunks:
            raise ValueError(f"No text chunks found for story {story['id']}")

        # Generate audio
        audio_dir = story_dir / "audio"
        audio_results = self.tts.synthesize_story(
            chunks, str(audio_dir), story["id"]
        )

        total_duration = sum(r["duration"] for r in audio_results)

        # Record in database
        for result in audio_results:
            self.db.insert_audio_record(
                story_id=story["id"],
                file_path=result["file_path"],
                duration=result["duration"],
                fmt=self.config.get("tts", {}).get("output_format", "mp3"),
            )

        # Update metadata with audio info
        metadata_path = story_dir / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["audio"] = {
                "total_duration_seconds": round(total_duration, 1),
                "num_parts": len(audio_results),
                "format": self.config.get("tts", {}).get("output_format", "mp3"),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))

        logger.info(
            "Audio generated: '%s' -> %d files, %.1f seconds total",
            story["title"][:40],
            len(audio_results),
            total_duration,
        )

        return {
            "story_id": story["id"],
            "title": story["title"],
            "audio_files": len(audio_results),
            "total_duration": round(total_duration, 1),
        }

    def _get_story_dir(self, story_id: str, category: str) -> Path:
        """Get the output directory for a story."""
        if self.organize_by_category:
            return self.output_base / category / story_id
        return self.output_base / story_id

    def get_stats(self) -> dict:
        """Get pipeline statistics."""
        return self.db.get_stats()

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
