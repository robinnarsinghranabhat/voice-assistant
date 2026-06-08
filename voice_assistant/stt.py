from __future__ import annotations

import io
import wave
from typing import Protocol, runtime_checkable

import numpy as np


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
        wav_bytes = recording_to_wav_bytes(recording, sample_rate)
        wav_file = io.BytesIO(wav_bytes)
        wav_file.name = "audio.wav"
        transcript = self._client.audio.transcriptions.create(
            model=self._model,
            file=wav_file,
        )
        return transcript.text
