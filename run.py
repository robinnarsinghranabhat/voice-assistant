import logging
import os
import queue
import signal
import threading

import numpy as np

_BASE = os.path.dirname(os.path.abspath(__file__))

class _RelPathFilter(logging.Filter):
    def filter(self, record):
        record.relpath = os.path.relpath(record.pathname, _BASE)
        return True

_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d [%(name)s] %(relpath)s:%(lineno)d %(message)s",
    datefmt="%H:%M:%S",
))
_handler.addFilter(_RelPathFilter())
logging.root.addHandler(_handler)
logging.root.setLevel(logging.INFO)
log = logging.getLogger("main")

from voice_assistant.ai_agent import ClaudeChat
from voice_assistant.audio_capture import AudioCapture
from voice_assistant.orchestrator import Orchestrator
from voice_assistant.ring_buffer import RingBuffer
from voice_assistant.stt import OpenAISTT
from voice_assistant.tts import OpenAITTS
from voice_assistant.vad import VoiceActivityDetector
from voice_assistant.wake_word import WakeWordDetector

from voice_assistant.stt import FasterWhisperSTT

SAMPLE_RATE = 16000


def main():
    ring_buffer = RingBuffer(capacity_ms=10000, sample_rate=SAMPLE_RATE)
    vad = VoiceActivityDetector(threshold=0.5, sample_rate=SAMPLE_RATE)
    wake_word = WakeWordDetector(
        model_path="/Users/rranabha/red_hat_repos/clawbench/voice_research/.venv/lib/python3.12/site-packages/openwakeword/resources/models/alexa_v0.1.onnx"
    )
    audio_capture = AudioCapture(sample_rate=SAMPLE_RATE)
    greeting = os.path.join(os.path.dirname(__file__), "hello.mp3")
    # interrupt_sound = os.path.join(os.path.dirname(__file__), "interrupt.wav")
    interrupt_sound = os.path.join(os.path.dirname(__file__), "freesound_community-swish-sound-94707.mp3")

    # stt = OpenAISTT()
    # Lot less Latency Observed
    stt = FasterWhisperSTT(model_size="base") # "base" or "small", "medium", "large-v3"
    chat = ClaudeChat()
    tts = OpenAITTS()
    tts.open_stream()

    def handle_capture(
        recording: list[np.ndarray],
        sample_rate: int,
        interrupt: threading.Event,
    ):
        text = stt.transcribe(recording, sample_rate)
        log.info("USER: %s", text)
        if interrupt.is_set() or not text.strip():
            return
        # TODO: each sentence is a separate TTS API call. To reduce gaps:
        #   - speak the first sentence immediately (low time-to-first-audio)
        #   - bundle subsequent sentences into fewer, larger TTS calls
        for sentence in chat.stream(text, interrupt):
            if interrupt.is_set():
                break
            tts.speak(sentence, interrupt)

    orchestrator = Orchestrator(
        ring_buffer=ring_buffer,
        wake_word=wake_word,
        debug=True,
        greeting_audio=greeting,
        interrupt_audio=interrupt_sound,
        on_capture_complete=handle_capture,
    )

    event_queue: queue.Queue = queue.Queue()

    def audio_callback(chunk):
        ring_buffer.write(chunk)
        vad_result = vad.process(chunk)
        event_queue.put((vad_result, chunk))

    def audio_thread():
        audio_capture.start(audio_callback)

    shutdown = threading.Event()

    def on_signal(_sig, _frame):
        log.info("Shutting down...")
        shutdown.set()
        audio_capture.stop()

    signal.signal(signal.SIGINT, on_signal)

    t = threading.Thread(target=audio_thread, daemon=True)
    t.start()

    log.info("Listening... say the wake word, then speak. Ctrl+C to quit")
    log.info("State: %s", orchestrator.state.value)

    while not shutdown.is_set():
        try:
            vad_result, chunk = event_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        orchestrator.on_audio(vad_result, chunk)


if __name__ == "__main__":
    main()
