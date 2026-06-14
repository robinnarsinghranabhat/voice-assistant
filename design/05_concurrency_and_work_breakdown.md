# Voice Assistant — Concurrency & Modules

## Threads

Four threads, but only two are always running. The other two are short-lived.

```
Thread 1 — Audio I/O (daemon, always running)
  Loops: stream.read() → ring_buffer.write() → vad.process() → queue.put()
  Born at startup, dies on shutdown.

Thread 2 — Main / Orchestrator (always running)
  Loops: queue.get() → orchestrator.on_audio()
  Runs the state machine, wake word detection, recording.

Thread 3 — Playback (daemon, spawned on demand)
  Runs afplay subprocess for greeting audio.
  Spawned when wake word detected. Dies when clip finishes.

Thread 4 — Processing (daemon, spawned on demand)
  Runs the full pipeline: STT → Claude streaming → TTS streaming.
  Spawned when CAPTURING finishes. Dies when pipeline completes.
  This is where the assistant "thinks and speaks."
```

## What blocks, what doesn't, and why it matters

Python's GIL means only one thread runs Python at a time — but C extensions
and I/O calls **release the GIL** while they wait. That's what makes this
program concurrent despite being single-process Python.

### Thread 1 — Audio I/O loop

```
stream.read(128)          ~8ms blocking wait for mic hardware.
                          GIL RELEASED (pyaudio is a C extension).
                          → This is the main window where Thread 2 gets to run.

ring_buffer.write(chunk)  Acquires a threading.Lock, copies 128 int16s via numpy.
                          GIL held, lock held — but it's a memcpy of 256 bytes.
                          Takes microseconds. Practically instant.

vad.process(chunk)        3 out of 4 calls: just appends to accumulator, returns None.
                          Negligible cost.
                          Every 4th call: runs Silero VAD inference via PyTorch.
                          GIL RELEASED during the torch compute (~1–2ms).

queue.put(...)            Thread-safe, essentially instant.
```

The key insight: Thread 1 spends most of its time in `stream.read()`, waiting
for the OS audio buffer to fill 128 samples. During that ~8ms wait, the GIL is
free. That's when Thread 2 processes the previous chunk through the orchestrator.

### Thread 2 — Orchestrator event loop

```
queue.get(timeout=0.1)    Blocks until a chunk arrives.
                          GIL RELEASED during the wait.
                          → Thread 1 runs freely while Thread 2 waits for events.

orchestrator.on_audio()   Pure Python: state checks, counters, conditionals.
                          In LISTENING state, also runs wake word inference.
                          Fast enough to finish before the next chunk arrives (~8ms).
```

Threads 1 and 2 naturally alternate: Thread 1 reads a chunk and posts it,
then blocks on the next read. Thread 2 picks up the event and processes it,
then blocks waiting for the next one. The queue is what decouples them.

### Thread 4 — Processing pipeline (STT → Claude → TTS)

```
stt.transcribe()          HTTP POST to OpenAI Whisper API.
                          GIL RELEASED during the network round-trip (~1–3s).

chat.stream()             HTTP streaming from Claude via Vertex AI.
                          GIL RELEASED while waiting for each text chunk.
                          Yields sentences as they arrive.

tts.speak()               HTTP streaming from OpenAI TTS API + PyAudio playback.
                          GIL RELEASED during both network I/O and audio output.
                          Each sentence is spoken as soon as it's ready.
```

Thread 4 is almost entirely I/O-bound. While it waits on HTTP responses and
audio output, Threads 1 and 2 keep running — the mic keeps capturing, the
orchestrator keeps processing, and wake word detection stays active. **This is
what makes interrupt detection work during processing.** The user can say the
wake word while the assistant is mid-sentence, and the orchestrator (Thread 2)
will detect it and set the interrupt Event, which Thread 4 checks between
sentences.

## Shared state and synchronization

```
Ring Buffer (threading.Lock)
  Thread 1 writes every chunk. Thread 2 reads lookback on state transitions.
  Lock contention is negligible — both operations are sub-microsecond memcpys.

Event Queue (queue.Queue, inherently thread-safe)
  Thread 1 puts (vad_result, chunk) tuples. Thread 2 gets them.
  The primary coordination mechanism between audio capture and orchestration.

Interrupt Event (threading.Event)
  Set by Thread 2 (orchestrator) when wake word detected during PROCESSING.
  Checked by Thread 4 (processing pipeline) between sentences.
  Causes Claude streaming and TTS playback to stop.

processing_done flag (bool on Orchestrator)
  Set by Thread 4 when pipeline completes. Checked by Thread 2.
  When true, orchestrator transitions PROCESSING → WAITING_FOR_USER.

Playback guard (float timestamp on Orchestrator)
  Set by Thread 3 (playback) with the greeting clip duration.
  Checked by Thread 2 — all on_audio() calls return early until guard expires.
```

## Why threads, not async

`stream.read()` is a blocking C call. In asyncio, it would block the entire
event loop — you'd need `run_in_executor` anyway, which is just threads with
extra steps. Threads are the natural fit because every I/O call in the system
(mic read, HTTP APIs, audio playback) is a C extension that releases the GIL.
We get real concurrency without async rewiring.

The GIL also means we don't need fine-grained locking for most shared state.
The ring buffer has a Lock because Thread 1 and Thread 2 access it, but
simple flags like `processing_done` are safe without a lock — Python's GIL
guarantees atomic reads/writes of simple attributes.

## Modules

```
AudioCapture         — mic → PCM chunks via pyaudio. Pure I/O, no processing logic.
RingBuffer           — circular numpy buffer, Lock-protected write/read.
VoiceActivityDetector — Silero VAD, 512-sample frame accumulation, torch inference.
WakeWordDetector     — openWakeWord, 1280-sample accumulation, streaming detection.
Orchestrator         — state machine (IDLE/LISTENING/WAITING/CAPTURING/PROCESSING).
                       Spawns Thread 4 for processing. Owns the interrupt Event.
OpenAISTT            — speech-to-text via OpenAI Whisper API. Swappable via Protocol.
ClaudeChat           — AI agent via Anthropic Vertex AI. Streams sentence-by-sentence.
                       Swappable via Protocol.
OpenAITTS            — text-to-speech via OpenAI API. Streams PCM to PyAudio output.
                       Swappable via Protocol.
audio_playback       — afplay wrapper for greeting audio (macOS only).
debug_utils          — save captured audio as .wav files.
```
