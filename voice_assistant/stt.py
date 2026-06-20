from __future__ import annotations

import io
import logging
import time
import wave
from typing import Protocol, runtime_checkable

import numpy as np

log = logging.getLogger("stt")


@runtime_checkable
class STT(Protocol):
    def transcribe(self, recording: list[np.ndarray], sample_rate: int) -> str: ...


def recording_to_wav_bytes(recording: list[np.ndarray], sample_rate: int) -> bytes:
    audio = np.concatenate(recording)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class OpenAISTT:
    def __init__(self, model: str = "whisper-1"):
        from openai import OpenAI

        self._client = OpenAI()
        self._model = model

    def transcribe(self, recording: list[np.ndarray], sample_rate: int) -> str:
        t0 = time.monotonic()
        wav_bytes = recording_to_wav_bytes(recording, sample_rate)
        wav_file = io.BytesIO(wav_bytes)
        wav_file.name = "audio.wav"
        transcript = self._client.audio.transcriptions.create(
            model=self._model,
            file=wav_file,
        )
        elapsed = time.monotonic() - t0
        log.info("OpenAI transcribed in %.2fs: %s", elapsed, transcript.text)
        return transcript.text


class FasterWhisperSTT:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, recording: list[np.ndarray], sample_rate: int) -> str:
        t0 = time.monotonic()
        audio = np.concatenate(recording).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments)
        elapsed = time.monotonic() - t0
        log.info("FasterWhisper transcribed in %.2fs: %s", elapsed, text)
        return text
