"""Optional CPU speech-to-text. Models must be installed locally in advance."""

import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

from meeting_pipeline import PipelineError

_inference_lock = Lock()


@lru_cache(maxsize=1)
def load_model(path):
    from faster_whisper import WhisperModel

    return WhisperModel(
        path, device="cpu", compute_type="int8", cpu_threads=2, local_files_only=True
    )


def decode_audio(path, max_seconds=1200):
    import av

    try:
        return _decode_audio(path, max_seconds)
    except av.error.FFmpegError:
        raise PipelineError("The uploaded audio could not be decoded.", 422) from None


def _decode_audio(path, max_seconds):
    import av
    import numpy as np

    chunks, samples = [], 0
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise PipelineError("The uploaded file has no audio stream.")
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=16000
        )
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                data = converted.to_ndarray().reshape(-1)
                samples += data.size
                if samples > max_seconds * 16000:
                    raise PipelineError(
                        f"Audio exceeds the {max_seconds // 60}-minute limit."
                    )
                chunks.append(data)
        for converted in resampler.resample(None):
            data = converted.to_ndarray().reshape(-1)
            samples += data.size
            if samples > max_seconds * 16000:
                raise PipelineError("Audio exceeds the duration limit.")
            chunks.append(data)
    if not samples:
        raise PipelineError("The uploaded file contains no audio.")
    return np.concatenate(chunks).astype("float32") / 32768.0


def transcribe_audio(path):
    configured = os.getenv("WHISPER_MODEL_PATH", "")
    if not configured or not Path(configured).is_dir():
        raise PipelineError(
            "Install the audio extra and configure WHISPER_MODEL_PATH with a local model directory.",
            503,
        )
    if not _inference_lock.acquire(blocking=False):
        raise PipelineError(
            "Another audio file is being transcribed. Please retry shortly.", 409
        )
    try:
        try:
            audio = decode_audio(path)
            model = load_model(str(Path(configured).resolve()))
            segments, info = model.transcribe(
                audio, beam_size=5, condition_on_previous_text=False
            )
            rows = []
            for segment in segments:
                if len(rows) >= 2000:
                    raise PipelineError(
                        "Too many transcript segments. Split the recording."
                    )
                rows.append(
                    {
                        "start": round(segment.start, 3),
                        "end": round(segment.end, 3),
                        "text": segment.text.strip(),
                    }
                )
            content = " ".join(r["text"] for r in rows).strip()
            if not content:
                raise PipelineError("No speech was detected.")
            return {
                "content": content,
                "segments": rows,
                "language": info.language,
                "duration_seconds": len(audio) / 16000,
            }
        except ImportError:
            raise PipelineError(
                "Audio dependencies are unavailable. Install requirements-audio.txt.",
                503,
            ) from None
        except PipelineError:
            raise
        except (ValueError, RuntimeError, OSError):
            raise PipelineError(
                "Audio could not be transcribed. Check that the file and local model are valid.",
                422,
            ) from None
    finally:
        _inference_lock.release()
