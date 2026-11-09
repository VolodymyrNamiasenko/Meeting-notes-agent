import importlib.util
import os
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audio_transcription as audio
from meeting_pipeline import PipelineError


@unittest.skipUnless(
    importlib.util.find_spec("av") and importlib.util.find_spec("numpy"),
    "Install requirements-audio.txt for decoder tests",
)
class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recording.wav"

    def wav(self, seconds, rate=8000, channels=2):
        with wave.open(str(self.path), "wb") as f:
            f.setnchannels(channels)
            f.setsampwidth(2)
            f.setframerate(rate)
            f.writeframes(b"\0\0" * int(rate * seconds) * channels)

    def test_real_decoder_resamples_stereo_to_bounded_mono(self):
        self.wav(0.5)
        result = audio.decode_audio(self.path)
        self.assertEqual(result.dtype.name, "float32")
        self.assertEqual(result.ndim, 1)
        self.assertEqual(len(result), 8000)

    def test_long_recording_rejected_during_decoding(self):
        self.wav(2)
        with self.assertRaises(PipelineError):
            audio.decode_audio(self.path, max_seconds=1)

    def test_malformed_audio_has_a_controlled_error(self):
        self.path.write_bytes(b"not a recording")
        with self.assertRaises(PipelineError) as error:
            audio.decode_audio(self.path)
        self.assertEqual(error.exception.status, 422)

    def test_segment_generator_is_consumed_and_timestamps_returned(self):
        import numpy as np

        model = SimpleNamespace(
            transcribe=lambda *a, **kw: (
                iter([SimpleNamespace(start=0.0, end=0.5, text=" Demo recording. ")]),
                SimpleNamespace(language="en"),
            )
        )
        with (
            patch.dict(os.environ, {"WHISPER_MODEL_PATH": self.temp.name}),
            patch.object(
                audio, "decode_audio", return_value=np.zeros(8000, dtype="float32")
            ),
            patch.object(audio, "load_model", return_value=model),
        ):
            result = audio.transcribe_audio(self.path)
        self.assertEqual(result["content"], "Demo recording.")
        self.assertEqual(
            result["segments"], [{"start": 0.0, "end": 0.5, "text": "Demo recording."}]
        )
        self.assertEqual(result["duration_seconds"], 0.5)

    def test_parallel_inference_is_rejected_without_loading_model(self):
        audio._inference_lock.acquire()
        try:
            with (
                patch.dict(os.environ, {"WHISPER_MODEL_PATH": self.temp.name}),
                patch.object(audio, "load_model") as load,
            ):
                with self.assertRaises(PipelineError) as error:
                    audio.transcribe_audio(self.path)
                self.assertEqual(error.exception.status, 409)
                load.assert_not_called()
        finally:
            audio._inference_lock.release()
