from __future__ import annotations

import logging
import os
import threading
import time
from typing import Protocol, runtime_checkable

import pyaudio

log = logging.getLogger("tts")


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

        self._client = OpenAI(timeout=15.0)
        self._model = model or os.environ.get("TTS_MODEL", "tts-1")
        self._voice = voice or os.environ.get("TTS_VOICE", "alloy")
        self._pa = pyaudio.PyAudio()
        self._stream: pyaudio.Stream | None = None

    def open_stream(self):
        if self._stream is not None:
            return
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True,
        )

    def close_stream(self):
        if self._stream is None:
            return
        self._stream.stop_stream()
        self._stream.close()
        self._stream = None

    def speak(self, text: str, interrupt: threading.Event | None = None) -> None:
        log.info("TTS start: %s", text)
        t0 = time.monotonic()
        owned_stream = self._stream is None
        if owned_stream:
            self.open_stream()
        try:
            with self._client.audio.speech.with_streaming_response.create(
                model=self._model,
                voice=self._voice,
                input=text,
                response_format="pcm",
            ) as response:
                for chunk in response.iter_bytes(chunk_size=4096):
                    if interrupt and interrupt.is_set():
                        log.info("TTS interrupted after %.2fs", time.monotonic() - t0)
                        break
                    self._stream.write(chunk)
        finally:
            if owned_stream:
                self.close_stream()
        log.info("TTS done in %.2fs", time.monotonic() - t0)
