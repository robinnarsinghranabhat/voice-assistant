import os
import queue
import signal
import threading

from voice_assistant.audio_capture import AudioCapture
from voice_assistant.orchestrator import Orchestrator
from voice_assistant.ring_buffer import RingBuffer
from voice_assistant.vad import VoiceActivityDetector
from voice_assistant.wake_word import WakeWordDetector

SAMPLE_RATE = 16000


def main():
    ring_buffer = RingBuffer(capacity_ms=10000, sample_rate=SAMPLE_RATE)
    vad = VoiceActivityDetector(threshold=0.5, sample_rate=SAMPLE_RATE)
    wake_word = WakeWordDetector(
        model_path="/Users/rranabha/red_hat_repos/clawbench/voice_research/.venv/lib/python3.12/site-packages/openwakeword/resources/models/alexa_v0.1.onnx"
    )
    audio_capture = AudioCapture(sample_rate=SAMPLE_RATE)
    greeting = os.path.join(os.path.dirname(__file__), "hello.mp3")
    orchestrator = Orchestrator(
        ring_buffer=ring_buffer,
        wake_word=wake_word,
        debug=True,
        greeting_audio=greeting,
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
        print("\nShutting down...")
        shutdown.set()
        audio_capture.stop()

    signal.signal(signal.SIGINT, on_signal)

    t = threading.Thread(target=audio_thread, daemon=True)
    t.start()

    print("Listening... (say the wake word, then speak. Ctrl+C to quit)")
    print(f"  State: {orchestrator.state.value}")

    while not shutdown.is_set():
        try:
            vad_result, chunk = event_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        orchestrator.on_audio(vad_result, chunk)


if __name__ == "__main__":
    main()
