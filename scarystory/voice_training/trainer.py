"""Voice cloning training module."""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Optimal recording specifications for voice training
RECORDING_SPECS = """
Voice Sample Recording Specifications
======================================

For best voice cloning results, follow these guidelines:

FORMAT:
  - Format: WAV (uncompressed) or FLAC
  - Sample rate: 44100 Hz (44.1 kHz) or higher
  - Bit depth: 16-bit or 24-bit
  - Channels: Mono (single channel)

DURATION:
  - Minimum: 2 minutes total across all samples
  - Recommended: 5-10 minutes for good quality
  - Optimal: 15-30 minutes for best results

CONTENT:
  - Read diverse text (news articles, stories, Wikipedia)
  - Include varied emotions and pacing
  - Mix short sentences with longer ones
  - Include questions and exclamations
  - Maintain a consistent speaking style throughout

ENVIRONMENT:
  - Quiet room with minimal echo
  - Use a quality microphone (USB condenser recommended)
  - Keep consistent distance from mic (6-12 inches)
  - Avoid background noise, fans, AC

TIPS:
  - Speak naturally, as if narrating a story
  - Keep a consistent volume level
  - Take breaks between segments
  - Re-record any sections with mistakes or noise
  - Name files sequentially: sample_001.wav, sample_002.wav, etc.
"""


class VoiceTrainer:
    """Handles voice sample processing and model training for voice cloning."""

    def __init__(self, config: dict[str, Any]):
        vt_config = config.get("voice_training", {})
        self.samples_dir = Path(vt_config.get("samples_dir", "voice_samples"))
        self.model_output_dir = Path(
            vt_config.get("model_output_dir", "trained_voices")
        )
        self.min_total_duration = vt_config.get("min_total_duration", 120)
        self.epochs = vt_config.get("epochs", 100)
        self.batch_size = vt_config.get("batch_size", 16)

    def validate_samples(self) -> dict[str, Any]:
        """Validate voice sample files and return info about them."""
        if not self.samples_dir.exists():
            self.samples_dir.mkdir(parents=True, exist_ok=True)
            return {
                "valid": False,
                "error": f"No samples found. Place WAV/FLAC files in: {self.samples_dir}",
                "samples": [],
                "total_duration": 0,
            }

        audio_extensions = {".wav", ".flac", ".mp3"}
        samples = [
            f
            for f in self.samples_dir.iterdir()
            if f.suffix.lower() in audio_extensions
        ]

        if not samples:
            return {
                "valid": False,
                "error": f"No audio files found in {self.samples_dir}",
                "samples": [],
                "total_duration": 0,
            }

        total_duration = 0
        sample_info = []

        for sample in sorted(samples):
            duration = self._get_sample_duration(sample)
            total_duration += duration
            sample_info.append(
                {
                    "path": str(sample),
                    "filename": sample.name,
                    "duration": round(duration, 1),
                    "size_mb": round(sample.stat().st_size / (1024 * 1024), 2),
                }
            )

        is_valid = total_duration >= self.min_total_duration

        result = {
            "valid": is_valid,
            "samples": sample_info,
            "total_duration": round(total_duration, 1),
            "min_required": self.min_total_duration,
            "sample_count": len(samples),
        }

        if not is_valid:
            result["error"] = (
                f"Total duration ({total_duration:.0f}s) is below "
                f"minimum ({self.min_total_duration}s). Add more samples."
            )

        return result

    def train_voice_model(self) -> dict[str, Any]:
        """Train a custom voice model using Coqui TTS XTTS fine-tuning.

        Returns dict with training results.
        """
        # Validate samples first
        validation = self.validate_samples()
        if not validation["valid"]:
            logger.error("Sample validation failed: %s", validation.get("error"))
            return {"success": False, "error": validation.get("error")}

        self.model_output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Starting voice training with %d samples (%.0fs total)",
            validation["sample_count"],
            validation["total_duration"],
        )

        try:
            return self._train_with_xtts(validation["samples"])
        except ImportError:
            logger.error(
                "Coqui TTS not installed. Install with: pip install TTS"
            )
            return {
                "success": False,
                "error": "Coqui TTS not installed. Install with: pip install TTS",
            }
        except Exception as e:
            logger.exception("Voice training failed")
            return {"success": False, "error": str(e)}

    def _train_with_xtts(self, samples: list[dict]) -> dict[str, Any]:
        """Fine-tune XTTS model on voice samples."""
        from TTS.api import TTS

        # For XTTS, we use the built-in fine-tuning approach:
        # 1. Prepare reference audio (combine/normalize samples)
        # 2. The XTTS model uses speaker embeddings at inference time
        #    rather than full fine-tuning for most use cases

        logger.info("Preparing voice samples for XTTS speaker embedding...")

        # For XTTS, the primary approach is zero-shot voice cloning
        # which uses reference audio at inference time. For fine-tuning,
        # we prepare the reference file.
        reference_path = self.model_output_dir / "reference_voice.wav"
        self._prepare_reference_audio(samples, str(reference_path))

        # Test the voice with a sample sentence
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        test_output = str(self.model_output_dir / "test_output.wav")

        tts.tts_to_file(
            text="This is a test of the custom voice model. How does it sound?",
            file_path=test_output,
            speaker_wav=str(reference_path),
            language="en",
        )

        logger.info("Voice model prepared. Reference: %s", reference_path)
        logger.info("Test output: %s", test_output)

        return {
            "success": True,
            "reference_path": str(reference_path),
            "test_output": str(test_output),
            "message": (
                "Voice reference prepared. Use this path in config.yaml "
                "under tts.coqui.custom_voice_path to use your voice."
            ),
        }

    def _prepare_reference_audio(
        self, samples: list[dict], output_path: str
    ) -> None:
        """Combine and normalize voice samples into a reference file."""
        try:
            from pydub import AudioSegment

            combined = AudioSegment.empty()

            for sample in samples:
                audio = AudioSegment.from_file(sample["path"])
                # Normalize to consistent volume
                audio = audio.set_channels(1)  # Mono
                audio = audio.set_frame_rate(22050)
                change_in_dbfs = -20.0 - audio.dBFS
                audio = audio.apply_gain(change_in_dbfs)
                combined += audio
                # Add small silence between samples
                combined += AudioSegment.silent(duration=500)

            # Trim to reasonable length (max 30 minutes)
            max_ms = 30 * 60 * 1000
            if len(combined) > max_ms:
                combined = combined[:max_ms]

            combined.export(output_path, format="wav")
            logger.info(
                "Reference audio prepared: %.1f seconds",
                len(combined) / 1000,
            )

        except ImportError:
            # Fallback: just use the first sample
            import shutil

            logger.warning(
                "pydub not available. Using first sample as reference."
            )
            shutil.copy2(samples[0]["path"], output_path)

    def _get_sample_duration(self, path: Path) -> float:
        """Get duration of an audio file in seconds."""
        try:
            import wave

            if path.suffix.lower() == ".wav":
                with wave.open(str(path), "rb") as wf:
                    return wf.getnframes() / float(wf.getframerate())
        except Exception:
            pass

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(str(path))
            return len(audio) / 1000.0
        except Exception:
            pass

        # Rough estimate from file size (assumes 16-bit 44.1kHz mono WAV)
        size = path.stat().st_size
        return size / (44100 * 2)

    @staticmethod
    def get_recording_specs() -> str:
        """Return optimal recording specifications for voice samples."""
        return RECORDING_SPECS
