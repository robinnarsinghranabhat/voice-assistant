import numpy as np
from openwakeword.model import Model

CHUNK_SIZE = 1280  # OpenWakeWord expects 1280-sample chunks (80ms at 16kHz)


class WakeWordDetector:
    def __init__(self, model_path: str | None = None, threshold: float = 0.5):
        if model_path:
            self._model = Model(wakeword_model_paths=[model_path])
        else:
            self._model = Model()
        self._threshold = threshold
        self._accumulator = np.array([], dtype=np.int16)
        self._model_names = list(self._model.models.keys())

    def process(self, chunk: np.ndarray) -> bool:
        self._accumulator = np.concatenate([self._accumulator, chunk])
        if len(self._accumulator) < CHUNK_SIZE:
            return False
        frame = self._accumulator[:CHUNK_SIZE]
        self._accumulator = self._accumulator[CHUNK_SIZE:]
        print("WAKE WORD CALLED")
        _test_ = self._model.predict(frame)
        for name in self._model_names:
            scores = list(self._model.prediction_buffer[name])
            # print(scores)
            if scores and scores[-1] > self._threshold:
                self._model.reset()
                return True

        return False

    def reset(self):
        self._accumulator = np.array([], dtype=np.int16)
        self._model.reset()
