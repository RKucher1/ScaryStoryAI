"""Text processing and cleaning for TTS-ready output."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class TextCleaner:
    """Cleans and formats Reddit story text for natural TTS narration."""

    def __init__(self, config: dict[str, Any]):
        processing = config.get("processing", {})
        self.chunk_max_words = processing.get("chunk_max_words", 800)
        self.remove_part_markers = processing.get("remove_part_markers", True)

    def clean(self, text: str) -> str:
        """Full cleaning pipeline for story text."""
        text = self._remove_reddit_formatting(text)
        text = self._remove_urls(text)
        text = self._remove_edits_and_updates(text)
        text = self._normalize_whitespace(text)
        text = self._expand_abbreviations(text)
        text = self._fix_punctuation_for_speech(text)

        if self.remove_part_markers:
            text = self._remove_series_markers(text)

        return text.strip()

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks suitable for TTS processing.

        Tries to split at paragraph boundaries, then sentence boundaries,
        keeping each chunk under the max word limit.
        """
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())

            # If a single paragraph exceeds the limit, split by sentences
            if para_words > self.chunk_max_words:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_words = 0
                chunks.extend(self._split_by_sentences(para))
                continue

            if current_words + para_words > self.chunk_max_words:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_words = para_words
            else:
                current_chunk.append(para)
                current_words += para_words

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split text by sentence boundaries, keeping under word limit."""
        # Split on sentence-ending punctuation followed by space
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = []
        current_words = 0

        for sentence in sentences:
            s_words = len(sentence.split())
            if current_words + s_words > self.chunk_max_words and current:
                chunks.append(" ".join(current))
                current = [sentence]
                current_words = s_words
            else:
                current.append(sentence)
                current_words += s_words

        if current:
            chunks.append(" ".join(current))

        return chunks

    def _remove_reddit_formatting(self, text: str) -> str:
        """Remove Reddit markdown formatting."""
        # Bold and italic
        text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
        text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text)

        # Superscript
        text = re.sub(r"\^(\S+)", r"\1", text)

        # Headers
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

        # Block quotes
        text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

        # Horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

        # Inline code and code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`(.+?)`", r"\1", text)

        # Reddit spoiler tags
        text = re.sub(r">!(.+?)!<", r"\1", text)

        # List markers
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

        return text

    def _remove_urls(self, text: str) -> str:
        """Remove URLs and Reddit-style links."""
        # Markdown links: keep text, remove URL
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Bare URLs
        text = re.sub(r"https?://\S+", "", text)
        return text

    def _remove_edits_and_updates(self, text: str) -> str:
        """Remove common Reddit edit notes and updates."""
        # "Edit:", "EDIT:", "Edit 1:", "Update:", etc.
        text = re.sub(
            r"^(?:Edit|EDIT|Update|UPDATE)\s*\d*\s*:.*$",
            "",
            text,
            flags=re.MULTILINE,
        )
        # "ETA:" (Edited To Add)
        text = re.sub(r"^ETA\s*:.*$", "", text, flags=re.MULTILINE)
        # "TL;DR" sections
        text = re.sub(r"(?i)tl;?\s*dr\s*:?.*$", "", text, flags=re.MULTILINE)
        # "Obligatory..." disclaimers
        text = re.sub(
            r"^(?:Obligatory|Sorry for|English is not|On mobile|Formatting).*$",
            "",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        return text

    def _remove_series_markers(self, text: str) -> str:
        """Remove nosleep-style series part markers."""
        text = re.sub(
            r"\[Part\s*\d+\]", "", text, flags=re.IGNORECASE
        )
        text = re.sub(
            r"\(Part\s*\d+\s*(?:of\s*\d+)?\)", "", text, flags=re.IGNORECASE
        )
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Clean up excess whitespace while preserving paragraph breaks."""
        # Normalize line endings
        text = text.replace("\r\n", "\n")
        # Remove trailing whitespace on lines
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
        # Collapse multiple blank lines to double newline
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text

    def _expand_abbreviations(self, text: str) -> str:
        """Expand common abbreviations for more natural speech."""
        replacements = {
            r"(?<!\w)w/o(?!\w)": "without",
            r"(?<!\w)w/(?!\w)": "with",
            r"(?<!\w)b/c(?!\w)": "because",
            r"\bidk\b": "I don't know",
            r"\bimo\b": "in my opinion",
            r"\bimho\b": "in my humble opinion",
            r"\btbh\b": "to be honest",
            r"\bsmh\b": "shaking my head",
            r"\bOMG\b": "oh my God",
            r"\bomg\b": "oh my God",
            r"\bbtw\b": "by the way",
            r"\bSO\b": "significant other",
            r"\bMIL\b": "mother in law",
            r"\bFIL\b": "father in law",
            r"\bSIL\b": "sister in law",
            r"\bBIL\b": "brother in law",
            r"\bOP\b": "the original poster",
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text)
        return text

    def _fix_punctuation_for_speech(self, text: str) -> str:
        """Adjust punctuation to improve TTS output."""
        # Add pause-inducing punctuation for natural reading
        # Multiple exclamation/question marks -> single
        text = re.sub(r"!{2,}", "!", text)
        text = re.sub(r"\?{2,}", "?", text)

        # Ellipsis standardization
        text = re.sub(r"\.{2,}", "...", text)

        # Remove parenthetical asides (often awkward in speech)
        text = re.sub(r"\s*\([^)]{0,50}\)\s*", " ", text)

        # Ensure sentences end with proper punctuation
        text = re.sub(r"([a-zA-Z])\n\n([A-Z])", r"\1.\n\n\2", text)

        return text
