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

### State Machine (4 states)
```
IDLE → LISTENING → WAITING_FOR_USER → CAPTURING → IDLE
```

- **IDLE**: VAD counts consecutive speech frames. After threshold (10 frames), transitions to LISTENING.
- **LISTENING**: Feeds ring buffer lookback (2s) to wake word, then streams live audio. On detection, plays greeting and transitions. On silence timeout (30 frames), resets to IDLE.
- **WAITING_FOR_USER**: Playback guard blocks processing during greeting. Then counts consecutive speech frames. After threshold (20 frames), grabs lookback and starts CAPTURING.
- **CAPTURING**: Records all chunks. On 1.5s silence, finalizes. Debug mode saves `.wav`.

### Key Design Patterns
- **VAD-gated wake word**: Wake word only runs after VAD confirms speech. Saves compute.
- **Lookback via ring buffer**: Audio before VAD confirmation is preserved and fed to wake word / recording.
- **Consecutive frame confirmation**: Multiple consecutive VAD hits required before state transitions. Prevents noise triggers.
- **Playback guard**: All audio processing paused during system audio output. Prevents self-triggering.
- **Every chunk to orchestrator**: Audio callback sends all chunks (not just VAD-triggered ones) so LISTENING gets continuous audio for the wake word model.

### Bugs Fixed Along the Way
- Ring buffer wrap-around logic was broken (shape mismatch on write)
- openWakeWord installed version uses `wakeword_model_paths` (not `wakeword_models`) and `models` (not `MODELS`)
- Wake word prediction_buffer empty on first frames — added guard
- Wake word only seeing 25% of audio in LISTENING (only VAD-triggered chunks were forwarded) — fixed by sending all chunks

## What's Next

### Phase 2: Speech-to-Text
- Choose STT approach (faster-whisper local vs API)
- Wire into orchestrator: CAPTURING done → transcribe audio → text
- New module: `voice_assistant/stt.py`

### Phase 3: LLM Integration
- Claude API via Anthropic SDK
- Conversational mode with message history
- New module: `voice_assistant/ai_agent.py`
- New state: PROCESSING (STT + LLM)

### Phase 4: Response TTS
- Text-to-speech for LLM responses
- Playback guard or AEC for echo handling during response
- New state: RESPONDING
- Stream response sentence-by-sentence

### Phase 5: Polish
- Interrupt detection during TTS (may need AEC)
- Multi-turn conversation flow
- Tool calling via LLM
- Configurable wake word
