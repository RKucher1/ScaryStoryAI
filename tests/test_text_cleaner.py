"""Tests for the text cleaner module."""

import pytest

from scarystory.processor.text_cleaner import TextCleaner

DEFAULT_CONFIG = {
    "processing": {
        "chunk_max_words": 800,
        "remove_part_markers": True,
    }
}


@pytest.fixture
def cleaner():
    return TextCleaner(DEFAULT_CONFIG)


class TestClean:
    def test_removes_bold_and_italic(self, cleaner):
        assert cleaner.clean("**bold** and *italic*") == "bold and italic"

    def test_removes_urls(self, cleaner):
        text = "Check out https://example.com for more"
        result = cleaner.clean(text)
        assert "https://" not in result
        assert "example.com" not in result

    def test_removes_markdown_links(self, cleaner):
        text = "Visit [this site](https://example.com) now"
        result = cleaner.clean(text)
        assert "this site" in result
        assert "https://" not in result

    def test_removes_edits(self, cleaner):
        text = "My story here.\n\nEdit: Thanks for the gold!"
        result = cleaner.clean(text)
        assert "Thanks for the gold" not in result

    def test_removes_tldr(self, cleaner):
        text = "Long story.\n\nTL;DR: short version"
        result = cleaner.clean(text)
        assert "short version" not in result

    def test_removes_part_markers(self, cleaner):
        text = "[Part 1] The beginning of my story"
        result = cleaner.clean(text)
        assert "[Part 1]" not in result
        assert "beginning" in result

    def test_removes_headers(self, cleaner):
        text = "## Chapter 1\n\nThe story begins"
        result = cleaner.clean(text)
        assert "##" not in result
        assert "Chapter 1" in result

    def test_removes_blockquotes(self, cleaner):
        text = "> quoted text\n\nNormal text"
        result = cleaner.clean(text)
        assert ">" not in result
        assert "quoted text" in result

    def test_removes_strikethrough(self, cleaner):
        text = "This is ~~wrong~~ right"
        result = cleaner.clean(text)
        assert "~~" not in result
        assert "wrong" in result

    def test_expands_abbreviations(self, cleaner):
        assert "with" in cleaner.clean("I went w/ my friend")
        assert "without" in cleaner.clean("He left w/o saying goodbye")
        assert "because" in cleaner.clean("I ran b/c I was scared")

    def test_normalizes_whitespace(self, cleaner):
        text = "First paragraph.\n\n\n\n\nSecond paragraph."
        result = cleaner.clean(text)
        assert "\n\n\n" not in result
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_removes_code_blocks(self, cleaner):
        text = "Normal text ```code here``` more text"
        result = cleaner.clean(text)
        assert "code here" not in result

    def test_removes_spoiler_tags(self, cleaner):
        text = "The killer was >!the butler!< all along"
        result = cleaner.clean(text)
        assert ">!" not in result
        assert "the butler" in result


class TestChunkText:
    def test_single_chunk_for_short_text(self, cleaner):
        text = "Short story. " * 10
        chunks = cleaner.chunk_text(text)
        assert len(chunks) == 1

    def test_splits_long_text(self, cleaner):
        # Create text longer than chunk_max_words
        paragraphs = ["This is a paragraph with several words. " * 20] * 10
        text = "\n\n".join(paragraphs)
        chunks = cleaner.chunk_text(text)
        assert len(chunks) > 1

    def test_preserves_all_content(self, cleaner):
        paragraphs = [f"Paragraph {i} content here." for i in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = cleaner.chunk_text(text)
        full_text = " ".join(chunks)
        for p in paragraphs:
            assert p in full_text

    def test_empty_text(self, cleaner):
        chunks = cleaner.chunk_text("")
        assert chunks == []


class TestFixPunctuation:
    def test_normalizes_multiple_exclamation(self, cleaner):
        result = cleaner.clean("Oh no!!!")
        assert result == "Oh no!"

    def test_normalizes_multiple_question(self, cleaner):
        result = cleaner.clean("What???")
        assert result == "What?"

    def test_normalizes_ellipsis(self, cleaner):
        result = cleaner.clean("And then...... silence")
        assert "......" not in result
        assert "..." in result
