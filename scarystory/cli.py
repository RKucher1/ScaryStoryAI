"""Command-line interface for ScaryStoryAI."""

import argparse
import json
import logging
import sys
from pathlib import Path

from scarystory.processor.pipeline import StoryPipeline
from scarystory.utils.config import load_config
from scarystory.utils.logging_setup import setup_logging
from scarystory.voice_training.trainer import VoiceTrainer

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScaryStoryAI - Reddit Story Scraper to Audio Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape top stories from this week
  python -m scarystory.cli scrape --sort top --time week

  # Process all unprocessed stories
  python -m scarystory.cli process

  # Generate audio for processed stories
  python -m scarystory.cli audio

  # Run the full pipeline (scrape + process + audio)
  python -m scarystory.cli run

  # Check voice samples and get recording specs
  python -m scarystory.cli voice --check
  python -m scarystory.cli voice --specs

  # Train voice model from samples
  python -m scarystory.cli voice --train

  # Show database stats
  python -m scarystory.cli stats

  # List top stories by category
  python -m scarystory.cli list --category stranger_danger --limit 10
        """,
    )

    parser.add_argument(
        "--config", type=str, default=None, help="Path to config file"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape stories from Reddit")
    scrape_parser.add_argument(
        "--sort",
        choices=["top", "hot", "new", "rising"],
        default="top",
        help="Sort method (default: top)",
    )
    scrape_parser.add_argument(
        "--time",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="week",
        help="Time filter for 'top' sort (default: week)",
    )
    scrape_parser.add_argument(
        "--subreddit",
        type=str,
        default=None,
        help="Scrape a specific subreddit only",
    )

    # Process command
    process_parser = subparsers.add_parser(
        "process", help="Process scraped stories (clean text)"
    )
    process_parser.add_argument(
        "--limit", type=int, default=50, help="Max stories to process"
    )

    # Audio command
    audio_parser = subparsers.add_parser(
        "audio", help="Generate audio for processed stories"
    )
    audio_parser.add_argument(
        "--limit", type=int, default=50, help="Max stories to generate audio for"
    )

    # Run command (full pipeline)
    run_parser = subparsers.add_parser(
        "run", help="Run full pipeline (scrape + process + audio)"
    )
    run_parser.add_argument(
        "--sort",
        choices=["top", "hot", "new", "rising"],
        default="top",
    )
    run_parser.add_argument(
        "--time",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="week",
    )

    # Voice training command
    voice_parser = subparsers.add_parser(
        "voice", help="Voice sample management and training"
    )
    voice_group = voice_parser.add_mutually_exclusive_group(required=True)
    voice_group.add_argument(
        "--check", action="store_true", help="Validate voice samples"
    )
    voice_group.add_argument(
        "--train", action="store_true", help="Train voice model"
    )
    voice_group.add_argument(
        "--specs", action="store_true", help="Show recording specifications"
    )

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # List command
    list_parser = subparsers.add_parser("list", help="List stories")
    list_parser.add_argument(
        "--category", type=str, default=None, help="Filter by category"
    )
    list_parser.add_argument(
        "--limit", type=int, default=20, help="Max stories to show"
    )

    # Web dashboard command
    web_parser = subparsers.add_parser("web", help="Launch web dashboard")
    web_parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)"
    )
    web_parser.add_argument(
        "--port", type=int, default=5000, help="Port to bind (default: 5000)"
    )
    web_parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    config = load_config(args.config)
    setup_logging(config)

    # Dispatch to command handler
    handlers = {
        "scrape": _cmd_scrape,
        "process": _cmd_process,
        "audio": _cmd_audio,
        "run": _cmd_run,
        "voice": _cmd_voice,
        "stats": _cmd_stats,
        "list": _cmd_list,
        "web": _cmd_web,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(config, args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_scrape(config: dict, args: argparse.Namespace) -> None:
    """Handle the scrape command."""
    with StoryPipeline(config) as pipeline:
        if args.subreddit:
            groups = {"custom": [args.subreddit]}
        else:
            groups = None

        print("Scraping stories from Reddit...")
        stories = pipeline.run_scrape(
            sort=args.sort,
            time_filter=args.time,
            subreddit_groups=groups,
        )

        print(f"\nScraped {len(stories)} new stories:")
        for story in stories[:10]:
            print(
                f"  [{story.get('score', 0):.1f}] [{story.get('category', '?')}] "
                f"{story['title'][:60]}"
            )
        if len(stories) > 10:
            print(f"  ... and {len(stories) - 10} more")


def _cmd_process(config: dict, args: argparse.Namespace) -> None:
    """Handle the process command."""
    with StoryPipeline(config) as pipeline:
        print("Processing stories...")
        results = pipeline.run_process(limit=args.limit)
        print(f"\nProcessed {len(results)} stories:")
        for r in results:
            print(f"  {r['story_id'][:8]}... -> {r['chunks']} chunks, {r['word_count']} words")


def _cmd_audio(config: dict, args: argparse.Namespace) -> None:
    """Handle the audio command."""
    with StoryPipeline(config) as pipeline:
        print("Generating audio (this may take a while)...")
        results = pipeline.run_generate_audio(limit=args.limit)
        print(f"\nGenerated audio for {len(results)} stories:")
        for r in results:
            print(
                f"  {r['title'][:50]} -> {r['audio_files']} files, "
                f"{r['total_duration']:.1f}s"
            )


def _cmd_run(config: dict, args: argparse.Namespace) -> None:
    """Handle the full pipeline run command."""
    with StoryPipeline(config) as pipeline:
        print("Running full pipeline (scrape -> process -> audio)...")
        result = pipeline.run_full_pipeline(sort=args.sort, time_filter=args.time)
        print("\nPipeline Results:")
        print(f"  Stories scraped: {result['new_stories_scraped']}")
        print(f"  Stories processed: {result['stories_processed']}")
        print(f"  Audio generated: {result['audio_generated']}")
        print(f"  Database stats: {result['database_stats']}")


def _cmd_voice(config: dict, args: argparse.Namespace) -> None:
    """Handle voice training commands."""
    trainer = VoiceTrainer(config)

    if args.specs:
        print(trainer.get_recording_specs())
        return

    if args.check:
        result = trainer.validate_samples()
        print("\nVoice Sample Validation:")
        print(f"  Samples found: {result.get('sample_count', 0)}")
        print(f"  Total duration: {result.get('total_duration', 0):.1f}s")
        print(f"  Minimum required: {result.get('min_required', 120)}s")
        print(f"  Valid: {'Yes' if result['valid'] else 'No'}")
        if not result["valid"]:
            print(f"  Error: {result.get('error', 'Unknown')}")
        if result.get("samples"):
            print("\n  Files:")
            for s in result["samples"]:
                print(f"    {s['filename']}: {s['duration']}s ({s['size_mb']}MB)")
        return

    if args.train:
        print("Starting voice model training...")
        result = trainer.train_voice_model()
        if result["success"]:
            print("\nTraining complete!")
            print(f"  Reference audio: {result['reference_path']}")
            print(f"  Test output: {result['test_output']}")
            print(f"  {result['message']}")
        else:
            print(f"\nTraining failed: {result['error']}")


def _cmd_stats(config: dict, args: argparse.Namespace) -> None:
    """Handle the stats command."""
    from scarystory.database.store import StoryDatabase

    db_path = config.get("database", {}).get("path", "scarystory.db")
    with StoryDatabase(db_path) as db:
        stats = db.get_stats()
        print("\nDatabase Statistics:")
        print(f"  Total stories: {stats.get('total', 0)}")
        print(f"  Processed: {stats.get('processed', 0)}")
        print(f"  Audio generated: {stats.get('audio_generated', 0)}")
        print(f"  Subreddits: {stats.get('subreddits', 0)}")
        print(f"  Categories: {stats.get('categories', 0)}")


def _cmd_list(config: dict, args: argparse.Namespace) -> None:
    """Handle the list command."""
    from scarystory.database.store import StoryDatabase

    db_path = config.get("database", {}).get("path", "scarystory.db")
    with StoryDatabase(db_path) as db:
        stories = db.get_top_stories(category=args.category, limit=args.limit)
        category_label = args.category or "all categories"
        print(f"\nTop {len(stories)} stories ({category_label}):")
        for story in stories:
            status = ""
            if story.get("is_audio_generated"):
                status = "[AUDIO]"
            elif story.get("is_processed"):
                status = "[PROCESSED]"
            print(
                f"  [{story.get('score', 0):.1f}] {status} "
                f"r/{story['subreddit']} - {story['title'][:55]}"
            )


def _cmd_web(config: dict, args: argparse.Namespace) -> None:
    """Handle the web dashboard command."""
    from scarystory.web import create_app

    app = create_app(config)
    print(f"\nScaryStoryAI Dashboard: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.\n")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
