import enum
import time

import numpy as np

from voice_assistant.audio_playback import play_audio
from voice_assistant.debug_utils import save_captured_audio
from voice_assistant.ring_buffer import RingBuffer
from voice_assistant.vad import VADResult
from voice_assistant.wake_word import WakeWordDetector


class State(enum.Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    CAPTURING = "CAPTURING"


LOOKBACK_MS = 300
SILENCE_TIMEOUT_S = 1.5
IDLE_TIMEOUT_S = 10.0
SAMPLE_RATE = 16000
VAD_CONFIRM_FRAMES = 10 # Look at 512 * 10 Frames
# WAKE_WORD_LOOKBACK_MS = 1000
WAKE_WORD_LOOKBACK_MS = 2000
SILENCE_RESET_FRAMES = 30 # Look at 512 * 20 Frames
WAKE_WORD_CHUNK_SIZE = 1280
CAPTURE_CONFIRM_FRAMES = 20
CAPTURE_LOOKBACK_MS = 500


class Orchestrator:
    def __init__(
        self,
        ring_buffer: RingBuffer,
        wake_word: WakeWordDetector,
        debug: bool = False,
        greeting_audio: str | None = None,
    ):
        self.state = State.IDLE
        self._ring_buffer = ring_buffer
        self._wake_word = wake_word
        self._greeting_audio = greeting_audio
        self._recording: list[np.ndarray] = []
        self._last_speech_time: float = 0.0
        self._state_entered_time: float = time.monotonic()
        self._consecutive_speech: int = 0
        self._consecutive_silence: int = 0
        self._lookback_fed: bool = False
        self._debug = debug
        self._playback_guard_until: float = 0.0

    def notify_playback_start(self, duration_s: float):
        self._playback_guard_until = time.monotonic() + duration_s

    def _is_playback_active(self) -> bool:
        return time.monotonic() < self._playback_guard_until

    def on_audio(self, vad_result: VADResult | None, chunk: np.ndarray):
        if self._is_playback_active():
            return
        if self.state == State.IDLE:
            if vad_result is not None:
                self._handle_idle(vad_result, chunk)
        elif self.state == State.LISTENING:
            self._handle_listening(vad_result, chunk)
        elif self.state == State.WAITING_FOR_USER:
            if vad_result is not None:
                self._handle_waiting(vad_result)
        elif self.state == State.CAPTURING:
            self._handle_capturing(vad_result, chunk)

    def _transition(self, new_state: State):
        print(f"  [{self.state.value}] → [{new_state.value}]")
        self.state = new_state
        self._state_entered_time = time.monotonic()

    def _on_wake_word_detected(self):
        if self._greeting_audio:
            play_audio(
                self._greeting_audio,
                on_start=lambda dur: self.notify_playback_start(dur),
            )

    def _handle_idle(self, result: VADResult, chunk: np.ndarray):
        if result.is_speech:
            print(result)
            self._consecutive_speech += 1
        else:
            self._consecutive_speech = 0
            return

        if self._consecutive_speech >= VAD_CONFIRM_FRAMES:
            self._consecutive_speech = 0
            self._consecutive_silence = 0
            self._lookback_fed = False
            self._transition(State.LISTENING)

    def _handle_listening(self, vad_result: VADResult | None, chunk: np.ndarray):
        if not self._lookback_fed:
            self._lookback_fed = True
            lookback = self._ring_buffer.read_last(WAKE_WORD_LOOKBACK_MS)
            for i in range(0, len(lookback), WAKE_WORD_CHUNK_SIZE):
                frame = lookback[i : i + WAKE_WORD_CHUNK_SIZE]
                if len(frame) == WAKE_WORD_CHUNK_SIZE:
                    if self._wake_word.process(frame):
                        print("Wake word detected!")
                        self._transition(State.WAITING_FOR_USER)
                        return

        detected = self._wake_word.process(chunk)
        if detected:
            print("Wake word detected!")
            time.sleep(1)
            self._on_wake_word_detected()
            self._transition(State.WAITING_FOR_USER)
            return

        if vad_result is not None:
            if vad_result.is_speech:
                self._consecutive_silence = 0
            else:
                self._consecutive_silence += 1

            if self._consecutive_silence >= SILENCE_RESET_FRAMES:
                self._wake_word.reset()
                self._consecutive_silence = 0
                self._transition(State.IDLE)

    def _handle_waiting(self, result: VADResult):
        now = time.monotonic()

        if result.is_speech:
            self._consecutive_speech += 1
        else:
            self._consecutive_speech = 0

        if self._consecutive_speech >= CAPTURE_CONFIRM_FRAMES:
            print("Speech confirmed — capturing...")
            self._consecutive_speech = 0
            lookback = self._ring_buffer.read_last(CAPTURE_LOOKBACK_MS)
            self._recording = [lookback]
            self._last_speech_time = now
            self._transition(State.CAPTURING)
            return

        if now - self._state_entered_time > IDLE_TIMEOUT_S:
            print("No speech detected, going back to idle.")
            self._transition(State.IDLE)

    def _handle_capturing(self, vad_result: VADResult | None, chunk: np.ndarray):
        self._recording.append(chunk)
        now = time.monotonic()

        if vad_result is None:
            return

        if vad_result.is_speech:
            self._last_speech_time = now
            return

        if now - self._last_speech_time >= SILENCE_TIMEOUT_S:
            total_samples = sum(len(c) for c in self._recording)
            duration = total_samples / SAMPLE_RATE
            print(f"Captured {duration:.1f}s of audio ({total_samples} samples)")
            if self._debug:
                save_captured_audio(self._recording, SAMPLE_RATE)
            self._recording = []
            self._transition(State.IDLE)
