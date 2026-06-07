from collections.abc import Callable

import numpy as np
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 16000
CHUNK = 128  # ~8ms at 16kHz


class AudioCapture:
    def __init__(self, sample_rate: int = SAMPLE_RATE, chunk_size: int = CHUNK):
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._audio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._running = False

    def start(self, callback: Callable[[np.ndarray], None]):
        self._audio = pyaudio.PyAudio()
        self._stream = self._audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=self._chunk_size,
        )
        self._running = True

        while self._running:
            raw = self._stream.read(self._chunk_size, exception_on_overflow=False)
            chunk = np.frombuffer(raw, dtype=np.int16)
            callback(chunk)

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._audio:
            self._audio.terminate()
