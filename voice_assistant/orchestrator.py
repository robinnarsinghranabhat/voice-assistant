import enum
import logging
import threading
import time
from collections.abc import Callable

import numpy as np

log = logging.getLogger("orchestrator")

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
    PROCESSING = "PROCESSING"


LOOKBACK_MS = 300
SILENCE_TIMEOUT_S = 3
IDLE_TIMEOUT_S = 10.0
SAMPLE_RATE = 16000
VAD_CONFIRM_FRAMES = 10 # Look at 512 * 10 Frames
# WAKE_WORD_LOOKBACK_MS = 1000
WAKE_WORD_LOOKBACK_MS = 2000
SILENCE_RESET_FRAMES = 30 # Look at 512 * 20 Frames
WAKE_WORD_CHUNK_SIZE = 1280
CAPTURE_CONFIRM_FRAMES = 20
CAPTURE_LOOKBACK_MS = 800 # 500


class Orchestrator:
    def __init__(
        self,
        ring_buffer: RingBuffer,
        wake_word: WakeWordDetector,
        debug: bool = False,
        greeting_audio: str | None = None,
        interrupt_audio: str | None = None,
        on_capture_complete: Callable[[list[np.ndarray], int, threading.Event], None] | None = None,
    ):
        self.state = State.IDLE
        self._ring_buffer = ring_buffer
        self._wake_word = wake_word
        self._greeting_audio = greeting_audio
        self._interrupt_audio = interrupt_audio
        self._on_capture_complete = on_capture_complete
        self._recording: list[np.ndarray] = []
        self._last_speech_time: float = 0.0
        self._state_entered_time: float = time.monotonic()
        self._consecutive_speech: int = 0
        self._consecutive_silence: int = 0
        self._lookback_fed: bool = False
        self._debug = debug
        self._playback_guard_until: float = 0.0
        self._interrupt = threading.Event()
        self._processing_done = False
        self._processing_cooldown_until: float = 0.0

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
        elif self.state == State.PROCESSING:
            self._handle_processing(vad_result, chunk)

    def _transition(self, new_state: State):
        log.info("%s → %s", self.state.value, new_state.value)
        self.state = new_state
        self._state_entered_time = time.monotonic()

    def _on_wake_word_detected(self):
        if self._greeting_audio:
            play_audio(
                self._greeting_audio,
                on_start=lambda dur: self.notify_playback_start(dur),
            )

    def _on_interrupt(self):
        self._interrupt.set()
        self._wake_word.reset()
        self._consecutive_speech = 0
        if self._interrupt_audio:
            play_audio(
                self._interrupt_audio,
                on_start=lambda dur: self.notify_playback_start(dur),
            )
        self._transition(State.WAITING_FOR_USER)

    def _handle_idle(self, result: VADResult, chunk: np.ndarray):
        # Gate: only enter LISTENING after sustained speech, not a single noisy frame.
        # Wake word model stays off here to save compute.
        if result.is_speech:
            log.debug("VAD speech: %.3f", result.confidence)
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
        # Lookback-then-realtime: VAD confirmation takes ~320ms, so the wake word
        # likely started before we entered LISTENING. First, replay the last 2s from
        # the ring buffer through the wake word model. If that doesn't find it,
        # switch to scanning live chunks as they arrive.
        if not self._lookback_fed:
            self._lookback_fed = True
            lookback = self._ring_buffer.read_last(WAKE_WORD_LOOKBACK_MS)
            for i in range(0, len(lookback), WAKE_WORD_CHUNK_SIZE):
                frame = lookback[i : i + WAKE_WORD_CHUNK_SIZE]
                if len(frame) == WAKE_WORD_CHUNK_SIZE:
                    if self._wake_word.process(frame):
                        log.info("Wake word detected (lookback)")
                        self._transition(State.WAITING_FOR_USER)
                        return

        detected = self._wake_word.process(chunk)
        if detected:
            log.info("Wake word detected (live)")
            self._on_wake_word_detected()
            self._transition(State.WAITING_FOR_USER)
            return

        # VAD result is None 3 out of 4 chunks (accumulating to 512 samples).
        # Only update silence tracking when we have an actual VAD decision.
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
        # Wake word was detected. Wait for the user to actually start speaking.
        # Lookback from ring buffer captures the start of their utterance that
        # arrived before VAD confirmed speech.
        now = time.monotonic()

        if result.is_speech:
            self._consecutive_speech += 1
        else:
            self._consecutive_speech = 0

        if self._consecutive_speech >= CAPTURE_CONFIRM_FRAMES:
            log.info("Speech confirmed — capturing")
            self._consecutive_speech = 0
            lookback = self._ring_buffer.read_last(CAPTURE_LOOKBACK_MS)
            self._recording = [lookback]
            self._last_speech_time = now
            self._transition(State.CAPTURING)
            return

        # After IDLE_TIMEOUT_S seconds, automatically switch to IDLE mode 
        if now - self._state_entered_time > IDLE_TIMEOUT_S:
            log.info("No speech detected, going back to idle")
            self._transition(State.IDLE)

    def _handle_capturing(self, vad_result: VADResult | None, chunk: np.ndarray):
        # Keep on appending new chunks to recording. When silence holds for SILENCE_TIMEOUT_S, hand off
        # the recording to a processing thread (STT → Claude → TTS) and move to
        # PROCESSING. The processing thread runs on its own — Threads 1+2 keep
        # capturing mic and running the orchestrator so we can detect interrupts.
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
            log.info("Captured %.1fs of audio (%d samples)", duration, total_samples)
            # if self._debug:
            #     save_captured_audio(self._recording, SAMPLE_RATE)
            recording = self._recording
            self._recording = []
            if self._on_capture_complete is not None:
                self._interrupt.clear()
                self._processing_done = False
                self._lookback_fed = False
                self._consecutive_silence = 0
                self._wake_word.reset()
                self._processing_cooldown_until = time.monotonic() + 2.0
                t = threading.Thread(
                    target=self._run_processing,
                    args=(recording,),
                    daemon=True,
                )
                t.start()
                self._transition(State.PROCESSING)
            else:
                self._transition(State.IDLE)

    def _run_processing(self, recording: list[np.ndarray]):
        try:
            self._on_capture_complete(recording, SAMPLE_RATE, self._interrupt)
        except Exception as e:
            log.error("Processing error: %s", e)
        self._processing_done = True

    def _handle_processing(self, vad_result: VADResult | None, chunk: np.ndarray):
        # While Thread 4 runs STT → Claude → TTS, this handler keeps listening
        # for the wake word so the user can interrupt mid-response.
        # Same lookback-then-realtime pattern as _handle_listening.
        if self._processing_done:
            self._wake_word.reset()
            self._consecutive_speech = 0
            self._transition(State.WAITING_FOR_USER)
            return

        if time.monotonic() < self._processing_cooldown_until:
            return

        if vad_result is None or not vad_result.is_speech:
            self._lookback_fed = False
            return

        if not self._lookback_fed:
            self._lookback_fed = True
            self._wake_word.reset()
            lookback = self._ring_buffer.read_last(WAKE_WORD_LOOKBACK_MS)
            for i in range(0, len(lookback), WAKE_WORD_CHUNK_SIZE):
                frame = lookback[i : i + WAKE_WORD_CHUNK_SIZE]
                if len(frame) == WAKE_WORD_CHUNK_SIZE:
                    if self._wake_word.process(frame):
                        self._on_interrupt()
                        return

        detected = self._wake_word.process(chunk)

        if detected:
            self._on_interrupt()
