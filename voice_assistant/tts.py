from __future__ import annotations

import os
import threading
from typing import Protocol, runtime_checkable

import pyaudio


@runtime_checkable
class TTS(Protocol):
    def speak(self, text: str, interrupt: threading.Event | None = None) -> None: ...


class OpenAITTS:
    def __init__(
        self,
        model: str | None = None,
        voice: str | None = None,
    ):
        from openai import OpenAI

        self._client = OpenAI()
        self._model = model or os.environ.get("TTS_MODEL", "tts-1")
        self._voice = voice or os.environ.get("TTS_VOICE", "alloy")
        self._pa = pyaudio.PyAudio()

    def speak(self, text: str, interrupt: threading.Event | None = None) -> None:
        with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="pcm",
        ) as response:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True,
            )
            try:
                for chunk in response.iter_bytes(chunk_size=4096):
                    if interrupt and interrupt.is_set():
                        break
                    stream.write(chunk)
            finally:
                stream.stop_stream()
                stream.close()
