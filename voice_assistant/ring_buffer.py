import threading

import numpy as np


class RingBuffer:
    def __init__(self, capacity_ms: int, sample_rate: int = 16000):
        self._capacity = int(sample_rate * capacity_ms / 1000)
        self._sample_rate = sample_rate
        self._buffer = np.zeros(self._capacity, dtype=np.int16)
        self._write_ptr = 0
        self._lock = threading.Lock()

    def write(self, chunk: np.ndarray):
        n = len(chunk)
        with self._lock:
            first = self._capacity - self._write_ptr
            if first >= n:
                self._buffer[self._write_ptr : self._write_ptr + n] = chunk
            else:
                self._buffer[self._write_ptr :] = chunk[:first]
                self._buffer[: n - first] = chunk[first:]
            self._write_ptr = (self._write_ptr + n) % self._capacity

    def read_last(self, ms: int) -> np.ndarray:
        n_samples = min(int(self._sample_rate * ms / 1000), self._capacity)
        with self._lock:
            start = (self._write_ptr - n_samples) % self._capacity
            if start < self._write_ptr:
                return self._buffer[start : self._write_ptr].copy()
            else:
                return np.concatenate(
                    [self._buffer[start:], self._buffer[: self._write_ptr]]
                )
