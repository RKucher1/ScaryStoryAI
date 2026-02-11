"""Text-to-Speech engine with multiple provider support."""

import io
import logging
import struct
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> float:
        """Synthesize text to audio file. Returns duration in seconds."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available/configured."""


class CoquiTTSProvider(TTSProvider):
    """Local TTS using Coqui TTS (free, open-source)."""

    def __init__(self, config: dict[str, Any]):
        self.coqui_config = config.get("tts", {}).get("coqui", {})
        self.model_name = self.coqui_config.get(
            "model_name", "tts_models/en/vctk/vits"
        )
        self.speaker = self.coqui_config.get("speaker")
        self.use_custom_voice = self.coqui_config.get("use_custom_voice", False)
        self.custom_voice_path = self.coqui_config.get("custom_voice_path", "")
        self.sample_rate = config.get("tts", {}).get("sample_rate", 22050)
        self._tts = None

    def _init_model(self) -> None:
        """Lazy-initialize the TTS model."""
        if self._tts is not None:
            return

        from TTS.api import TTS

        logger.info("Loading Coqui TTS model: %s", self.model_name)

        if self.use_custom_voice and self.custom_voice_path:
            # Use XTTS for voice cloning with custom voice
            self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            logger.info("Using custom voice: %s", self.custom_voice_path)
        else:
            self._tts = TTS(self.model_name)

        logger.info("Coqui TTS model loaded")

    def synthesize(self, text: str, output_path: str) -> float:
        self._init_model()

        if self.use_custom_voice and self.custom_voice_path:
            self._tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker_wav=self.custom_voice_path,
                language="en",
            )
        elif self.speaker:
            self._tts.tts_to_file(
                text=text,
                file_path=output_path,
                speaker=self.speaker,
            )
        else:
            self._tts.tts_to_file(text=text, file_path=output_path)

        return _get_audio_duration(output_path)

    def is_available(self) -> bool:
        try:
            import TTS  # noqa: F401

            return True
        except ImportError:
            return False


class ElevenLabsTTSProvider(TTSProvider):
    """Cloud TTS using ElevenLabs API (paid, high quality)."""

    def __init__(self, config: dict[str, Any]):
        self.el_config = config.get("tts", {}).get("elevenlabs", {})
        self.api_key = self.el_config.get("api_key", "")
        self.voice_id = self.el_config.get("voice_id", "")
        self.model_id = self.el_config.get(
            "model_id", "eleven_multilingual_v2"
        )
        self.stability = self.el_config.get("stability", 0.5)
        self.similarity_boost = self.el_config.get("similarity_boost", 0.75)

    def synthesize(self, text: str, output_path: str) -> float:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=self.api_key)

        audio_generator = client.text_to_speech.convert(
            voice_id=self.voice_id,
            text=text,
            model_id=self.model_id,
            voice_settings={
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
            },
        )

        # Collect all audio data from the generator
        audio_data = b"".join(audio_generator)

        with open(output_path, "wb") as f:
            f.write(audio_data)

        return _get_audio_duration(output_path)

    def is_available(self) -> bool:
        if not self.api_key or self.api_key.startswith("YOUR_"):
            return False
        try:
            import elevenlabs  # noqa: F401

            return True
        except ImportError:
            return False


class BarkTTSProvider(TTSProvider):
    """Local TTS using Suno Bark (free, expressive)."""

    def __init__(self, config: dict[str, Any]):
        self.sample_rate = config.get("tts", {}).get("sample_rate", 22050)

    def synthesize(self, text: str, output_path: str) -> float:
        from bark import SAMPLE_RATE, generate_audio, preload_models
        from scipy.io.wavfile import write as write_wav

        preload_models()
        audio_array = generate_audio(text)

        # Write WAV first
        wav_path = output_path.rsplit(".", 1)[0] + ".wav"
        write_wav(wav_path, SAMPLE_RATE, audio_array)

        # Convert to target format if needed
        if output_path.endswith(".mp3"):
            _wav_to_mp3(wav_path, output_path)
            Path(wav_path).unlink(missing_ok=True)
        elif wav_path != output_path:
            Path(wav_path).rename(output_path)

        return _get_audio_duration(output_path)

    def is_available(self) -> bool:
        try:
            import bark  # noqa: F401

            return True
        except ImportError:
            return False


class TTSEngine:
    """Main TTS engine that delegates to the configured provider."""

    PROVIDERS = {
        "coqui": CoquiTTSProvider,
        "elevenlabs": ElevenLabsTTSProvider,
        "bark": BarkTTSProvider,
    }

    def __init__(self, config: dict[str, Any]):
        self.config = config
        provider_name = config.get("tts", {}).get("provider", "coqui")
        self.output_format = config.get("tts", {}).get("output_format", "mp3")

        if provider_name not in self.PROVIDERS:
            raise ValueError(
                f"Unknown TTS provider: {provider_name}. "
                f"Available: {list(self.PROVIDERS.keys())}"
            )

        self.provider = self.PROVIDERS[provider_name](config)

        if not self.provider.is_available():
            logger.warning(
                "TTS provider '%s' is not available. "
                "Check dependencies and configuration.",
                provider_name,
            )
        else:
            logger.info("TTS engine initialized with provider: %s", provider_name)

    def synthesize_story(
        self,
        chunks: list[str],
        output_dir: str,
        story_id: str,
    ) -> list[dict[str, Any]]:
        """Synthesize all chunks of a story to audio files.

        Returns list of dicts with file_path and duration for each chunk.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = []
        for i, chunk in enumerate(chunks):
            filename = f"{story_id}_part{i:03d}.{self.output_format}"
            filepath = str(output_path / filename)

            logger.info(
                "Synthesizing chunk %d/%d (%d chars)",
                i + 1,
                len(chunks),
                len(chunk),
            )

            try:
                duration = self.provider.synthesize(chunk, filepath)
                results.append(
                    {
                        "file_path": filepath,
                        "duration": duration,
                        "chunk_index": i,
                        "text_length": len(chunk),
                    }
                )
                logger.info(
                    "Generated: %s (%.1f seconds)", filename, duration
                )
            except Exception:
                logger.exception("Failed to synthesize chunk %d", i)
                continue

        return results

    def synthesize_single(self, text: str, output_path: str) -> float:
        """Synthesize a single text to an audio file. Returns duration."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return self.provider.synthesize(text, output_path)


def _get_audio_duration(file_path: str) -> float:
    """Get duration of an audio file in seconds."""
    path = Path(file_path)

    if path.suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate) if rate else 0.0
        except Exception:
            pass

    if path.suffix == ".mp3":
        try:
            return _estimate_mp3_duration(str(path))
        except Exception:
            pass

    return 0.0


def _estimate_mp3_duration(file_path: str) -> float:
    """Estimate MP3 duration from file size and bitrate header."""
    with open(file_path, "rb") as f:
        header = f.read(4)
        if len(header) < 4:
            return 0.0

        # Check for ID3 tag and skip it
        if header[:3] == b"ID3":
            f.seek(6)
            size_bytes = f.read(4)
            if len(size_bytes) < 4:
                return 0.0
            tag_size = (
                (size_bytes[0] << 21)
                | (size_bytes[1] << 14)
                | (size_bytes[2] << 7)
                | size_bytes[3]
            )
            f.seek(10 + tag_size)
            header = f.read(4)
            if len(header) < 4:
                return 0.0

        # Find sync word
        if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
            # Parse MPEG audio header for bitrate
            version = (header[1] >> 3) & 0x03
            layer = (header[1] >> 1) & 0x03
            bitrate_index = (header[2] >> 4) & 0x0F

            # MPEG1 Layer 3 bitrate table (kbps)
            bitrates_v1_l3 = [
                0, 32, 40, 48, 56, 64, 80, 96,
                112, 128, 160, 192, 224, 256, 320, 0,
            ]

            if version == 3 and layer == 1 and 1 <= bitrate_index <= 14:
                bitrate = bitrates_v1_l3[bitrate_index] * 1000
            else:
                bitrate = 192000  # fallback

            file_size = Path(file_path).stat().st_size
            return (file_size * 8) / bitrate if bitrate else 0.0

    # Fallback: estimate from file size assuming 192kbps
    file_size = Path(file_path).stat().st_size
    return (file_size * 8) / 192000


def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k") -> None:
    """Convert WAV to MP3 using pydub/ffmpeg."""
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_wav(wav_path)
        audio.export(mp3_path, format="mp3", bitrate=bitrate)
    except ImportError:
        logger.warning(
            "pydub not available for WAV->MP3 conversion. Keeping WAV format."
        )
        import shutil
        shutil.copy2(wav_path, mp3_path)
