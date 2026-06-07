import os
import wave
from datetime import datetime

import numpy as np

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_captures")


def save_captured_audio(
    recording: list[np.ndarray],
    sample_rate: int = 16000,
    label: str = "",
) -> str:
    os.makedirs(DEBUG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    filename = f"capture_{timestamp}{suffix}.wav"
    filepath = os.path.join(DEBUG_DIR, filename)

    audio = np.concatenate(recording)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())

    duration = len(audio) / sample_rate
    print(f"  [DEBUG] Saved {duration:.1f}s capture → {filepath}")
    return filepath
