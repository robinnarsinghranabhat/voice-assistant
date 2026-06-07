from dataclasses import dataclass

import numpy as np
import torch

from silero_vad import load_silero_vad

torch.set_num_threads(1)

FRAME_SIZE = 512  # Silero's minimum at 16kHz


@dataclass
class VADResult:
    is_speech: bool
    confidence: float


class VoiceActivityDetector:
    def __init__(self, threshold: float = 0.2, sample_rate: int = 16000):
        self._model = load_silero_vad()
        self._threshold = threshold
        self._sample_rate = sample_rate
        self._accumulator = np.array([], dtype=np.int16)

    def process(self, chunk: np.ndarray) -> VADResult | None:
        self._accumulator = np.concatenate([self._accumulator, chunk])
        if len(self._accumulator) < FRAME_SIZE:
            return None

        frame = self._accumulator[:FRAME_SIZE]
        self._accumulator = self._accumulator[FRAME_SIZE:]

        audio_float = frame.astype(np.float32) / 32768.0
        confidence = self._model(
            torch.from_numpy(audio_float), self._sample_rate
        ).item()

        return VADResult(
            is_speech=confidence >= self._threshold,
            confidence=confidence,
        )
