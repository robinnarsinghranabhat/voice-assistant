# Voice Assistant — Progress

## What's Built

### Audio Pipeline (working end-to-end)
- **AudioCapture**: Mic input via pyaudio, 128-sample chunks at 16kHz
- **RingBuffer**: Circular numpy buffer (configurable capacity, currently 10s), thread-safe
- **VAD**: Silero VAD wrapper, 512-sample frames, returns speech/no-speech with confidence
- **WakeWordDetector**: openWakeWord with alexa model (`.onnx`), streaming 1280-sample chunks
- **Orchestrator**: State machine with playback guard
- **Audio Playback**: `afplay` wrapper (macOS), threaded, with duration detection
- **Debug Utils**: Save captured audio as timestamped `.wav` files

### State Machine (5 states)
```
IDLE → LISTENING → WAITING_FOR_USER → CAPTURING → PROCESSING → WAITING_FOR_USER
```

- **IDLE**: VAD counts consecutive speech frames. After threshold (10 frames), transitions to LISTENING.
- **LISTENING**: Feeds ring buffer lookback (2s) to wake word, then streams live audio. On detection, plays greeting and transitions. On silence timeout (30 frames), resets to IDLE.
- **WAITING_FOR_USER**: Playback guard blocks processing during greeting. Then counts consecutive speech frames. After threshold (20 frames), grabs lookback and starts CAPTURING. Times out to IDLE after 10s of no speech.
- **CAPTURING**: Records all chunks. On 1.5s silence, finalizes and transitions to PROCESSING.
- **PROCESSING**: STT + LLM + TTS run on a worker thread. Main loop continues VAD and wake word detection for interrupt support. On completion, transitions to WAITING_FOR_USER (conversation sustains). On wake word interrupt, cancels processing and transitions to WAITING_FOR_USER.

### Key Design Patterns
- **VAD-gated wake word**: Wake word only runs after VAD confirms speech. Saves compute.
- **Lookback via ring buffer**: Audio before VAD confirmation is preserved and fed to wake word / recording.
- **Consecutive frame confirmation**: Multiple consecutive VAD hits required before state transitions. Prevents noise triggers.
- **Playback guard**: All audio processing paused during system audio output. Prevents self-triggering.
- **Every chunk to orchestrator**: Audio callback sends all chunks (not just VAD-triggered ones) so LISTENING gets continuous audio for the wake word model.
- **Swappable backends via Protocol**: STT, AI agent, and TTS each define a `typing.Protocol`. Swap implementations by changing one line in `run.py`.
- **Threaded processing with interrupt**: STT + LLM + TTS run on a daemon thread. Main loop stays responsive for wake word interrupt detection.
- **Streaming TTS pipeline**: LLM response streams sentence-by-sentence → each sentence sent to TTS → raw PCM audio streams directly to PyAudio speakers. Interrupt checks between audio chunks for mid-sentence cancel.
- **Processing cooldown**: 2-second cooldown after entering PROCESSING prevents tail-end speech from triggering false wake word detection.
- **Conversation sustain**: After PROCESSING completes, transitions to WAITING_FOR_USER (not IDLE) so multi-turn conversation flows without re-saying the wake word.

### Speech-to-Text (Phase 2 — done)
- **OpenAISTT**: Whisper API, converts recording to in-memory WAV via `recording_to_wav_bytes()`, swappable via `STT` Protocol
- New module: `voice_assistant/stt.py`

### LLM Integration (Phase 3 — done)
- **ClaudeChat**: Claude via Anthropic Vertex AI SDK, multi-turn conversation history
- Streaming support: `stream()` method yields sentences as they arrive from the LLM
- Swappable via `ChatAgent` Protocol
- Config via env vars: `CLOUD_ML_REGION`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLAUDE_MODEL`, `CLAUDE_MAX_TOKENS`
- New module: `voice_assistant/ai_agent.py`

### Response TTS (Phase 4 — done)
- **OpenAITTS**: OpenAI TTS API, streams raw PCM (24kHz, 16-bit, mono) directly to PyAudio
- No temp files — audio plays as bytes arrive from the API
- Interrupt support: checks `threading.Event` between audio chunks
- Swappable via `TTS` Protocol
- New module: `voice_assistant/tts.py`

### Interrupt Support (done)
- Wake word detection continues during PROCESSING via VAD-gated wake word with ring buffer lookback
- Interrupt cancels LLM streaming (per-token check) and TTS playback (per-chunk check)
- 2-second cooldown prevents false triggers from tail-end speech

### Bugs Fixed Along the Way
- Ring buffer wrap-around logic was broken (shape mismatch on write)
- openWakeWord installed version uses `wakeword_model_paths` (not `wakeword_models`) and `models` (not `MODELS`)
- Wake word prediction_buffer empty on first frames — added guard
- Wake word only seeing 25% of audio in LISTENING (only VAD-triggered chunks were forwarded) — fixed by sending all chunks
- False wake word triggers during PROCESSING from captured speech tail — fixed with wake word reset + cooldown
- False wake word triggers during TTS playback — fixed with VAD gating (only feed speech-confirmed audio to wake word)

## What's Next

### Phase 5: Polish
- Echo cancellation for speaker mode (currently requires airpods)
- Tool calling via LLM (the `ChatAgent` protocol supports this — implementation in `ClaudeChat`)
- Custom wake word training for interrupt (instead of reusing "Alexa")
- Configurable wake word
- Conversation history truncation for long sessions
