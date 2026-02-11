# ScaryStoryAI

Reddit Story Scraper to Audio Converter for faceless YouTube video production.

## Features

- **Reddit Scraping** - Ethical API-based scraping via PRAW from horror/scary story subreddits
- **Smart Scoring** - Engagement-based ranking with keyword category matching and AI-content detection
- **Text Processing** - Cleans Reddit markdown, expands abbreviations, chunks text for TTS
- **Multi-Provider TTS** - Supports Coqui TTS (free/local), ElevenLabs (cloud), and Bark (local/expressive)
- **Voice Cloning** - Train custom voice models from your own voice samples
- **Deduplication** - SQLite database prevents re-scraping the same stories
- **Category Organization** - Stories auto-classified into topics (stranger danger, workplace horror, etc.)

## Quick Start

### 1. Install

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

For specific TTS providers:
```bash
# Coqui TTS (free, local - recommended to start)
pip install TTS

# ElevenLabs (cloud, high quality - requires API key)
pip install elevenlabs

# Bark (free, local, expressive - requires GPU)
pip install bark scipy
```

### 2. Configure

```bash
cp config.yaml config.local.yaml
```

Edit `config.local.yaml` with your Reddit API credentials:
```yaml
reddit:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  user_agent: "ScaryStoryAI/1.0 (by /u/your_username)"
```

Get Reddit API credentials at: https://www.reddit.com/prefs/apps/

Alternatively, set environment variables:
```bash
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
```

### 3. Run

```bash
# Scrape top stories from this week
python -m scarystory scrape --sort top --time week

# Process scraped stories (clean text, generate transcripts)
python -m scarystory process

# Generate audio narration
python -m scarystory audio

# Or run the full pipeline at once
python -m scarystory run
```

## Commands

| Command | Description |
|---------|-------------|
| `scrape` | Scrape stories from configured subreddits |
| `process` | Clean text and generate transcripts for scraped stories |
| `audio` | Generate TTS audio for processed stories |
| `run` | Full pipeline (scrape + process + audio) |
| `voice --check` | Validate voice sample recordings |
| `voice --train` | Train custom voice model from samples |
| `voice --specs` | Show optimal recording specifications |
| `stats` | Show database statistics |
| `list` | List top stories, optionally by category |

## Voice Cloning

To use your own voice:

1. Record voice samples (see `python -m scarystory voice --specs` for guidelines)
2. Place WAV/FLAC files in `voice_samples/`
3. Validate: `python -m scarystory voice --check`
4. Train: `python -m scarystory voice --train`
5. Update `config.local.yaml`:
   ```yaml
   tts:
     provider: coqui
     coqui:
       use_custom_voice: true
       custom_voice_path: "trained_voices/reference_voice.wav"
   ```

## Output Structure

```
output/
  stranger_danger/
    <story-id>/
      transcript.txt      # Clean text ready for reading
      metadata.json       # Title, source, category, stats, duration
      chunks/
        chunk_000.txt     # Text chunks for TTS
        chunk_001.txt
      audio/
        <story-id>_part000.mp3
        <story-id>_part001.mp3
  workplace_horror/
    ...
```

## Configuration

All settings are in `config.yaml`. Create `config.local.yaml` for local overrides (credentials, custom settings). Environment variables override both:

| Env Variable | Config Path |
|---|---|
| `REDDIT_CLIENT_ID` | `reddit.client_id` |
| `REDDIT_CLIENT_SECRET` | `reddit.client_secret` |
| `REDDIT_USERNAME` | `reddit.username` |
| `REDDIT_PASSWORD` | `reddit.password` |
| `ELEVENLABS_API_KEY` | `tts.elevenlabs.api_key` |

## Testing

```bash
pip install pytest
pytest tests/
```

## Extending to Other Content Types

The system is designed for easy adaptation. To scrape motivational stories instead:

1. Add new subreddits to `config.yaml`:
   ```yaml
   subreddits:
     motivational:
       - "GetMotivated"
       - "MadeMeSmile"
   ```

2. Add new category keywords:
   ```yaml
   categories:
     success_story:
       keywords: ["overcame", "achieved", "finally did it"]
       weight: 1.5
   ```

3. Run with the same commands - the pipeline handles the rest.
