# Voice Assistant — Concurrency & Module Breakdown

## Current Threading Model

```
Thread 1: Audio I/O (daemon)
  AudioCapture.start(callback)  ← blocks on mic.read()
  callback: ring_buffer.write() → vad.process() → queue.put()
  Never blocks on anything except mic.read(). ~10ms per loop.

Thread 2: Main thread (orchestrator event loop)
  queue.get() → orchestrator.on_audio()
  State machine logic, wake word processing, recording.

Thread 3: Playback (daemon, spawned on demand)
  afplay subprocess for greeting audio.
  Spawned when wake word detected, dies when playback done.
```

## Shared State

```
Ring Buffer:        Thread 1 writes, Thread 2 reads (Lock-protected)
Event Queue:        Thread 1 writes, Thread 2 reads (thread-safe Queue)
Playback guard:     Thread 3 sets timestamp, Thread 2 checks (float, atomic-ish)
```

## Why Threads, Not Async

mic.read() blocks. While it blocks, nothing else runs in asyncio.
Threads let mic capture continue while orchestrator processes events.
Python GIL caveat doesn't matter: mic.read() releases GIL (C extension),
and our Python logic per chunk is <1ms.

## Implemented Modules

```
AudioCapture       — mic → PCM chunks via pyaudio callback
RingBuffer         — circular numpy buffer, thread-safe write/read
VoiceActivityDetector — Silero VAD wrapper, 512-sample frame accumulation
WakeWordDetector   — openWakeWord wrapper, 1280-sample accumulation, streaming
Orchestrator       — state machine (IDLE/LISTENING/WAITING/CAPTURING)
audio_playback     — afplay wrapper with duration detection
debug_utils        — save captured audio as .wav files
```

## Next Modules (Not Yet Built)

```
SpeechToText       — convert captured audio → text
                     Options: faster-whisper (local) or API-based
                     Input: int16 PCM array
                     Output: str

AIAgent            — LLM conversation layer
                     Claude API via Anthropic SDK
                     Input: user text + conversation history
                     Output: response text (streamed)
                     Future: tool calling

TextToSpeech       — convert response text → audio → speaker
                     Options: piper (local) or ElevenLabs (API)
                     Needs playback guard or AEC integration

AEC (future)       — acoustic echo cancellation
                     Needed if we want user to interrupt during TTS
                     Current playback guard is simpler alternative
```

## Integration Point

CAPTURING → IDLE currently just prints duration and optionally saves .wav.
Next step: CAPTURING → PROCESSING (STT → LLM → TTS → back to WAITING or IDLE).
