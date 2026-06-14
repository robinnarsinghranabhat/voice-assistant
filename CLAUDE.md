# Voice Assistant

Tested on macOS.

## Quickstart

```bash
# 1. Install system dependency (macOS)
brew install portaudio

# 2. Install Python dependencies
uv sync

# 3. Download wake word model
uv run python -c "from openwakeword.utils import download_models; download_models()"

# 4. Set environment variables
export OPENAI_API_KEY="sk-..."                          # for Whisper STT + TTS
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id" # for Claude AI agent
export CLOUD_ML_REGION="us-east5"                        # optional, defaults to us-east5

# 5. Authenticate with Google Cloud (for Claude via Vertex AI)
gcloud auth application-default login

# 6. Run
uv run python run.py
```

Say "Alexa" to start, speak your question, and the assistant will respond via voice. The conversation sustains — just keep talking. Say "Alexa" again to interrupt the assistant mid-response.

## Setup

- Package manager: `uv`
- Python: 3.12
- Virtual env: `.venv` (local to this directory)

## Common commands

- Install a package: `uv add <package>`
- Remove a package: `uv remove <package>`
- Run a script: `uv run python <script.py>`
- Run the assistant: `uv run python run.py`
- Activate venv manually: `source .venv/bin/activate`

## Project Status

See [Progress.md](Progress.md) for what's built, key design decisions, and what's next.

## Architecture

Design docs in `design/`:
- `01_state_machine.md` — State machine: IDLE → LISTENING → WAITING_FOR_USER → CAPTURING → PROCESSING
- `02_component_data_flow.md` — Components, data formats, threading model
- `03_sequence_happy_path.md` — Step-by-step timing of the happy path
- `04_audio_signal_flow.md` — Audio formats, ring buffer, VAD/wake word accumulation
- `05_concurrency_and_work_breakdown.md` — Threading, shared state, module breakdown

## Code Structure

```
run.py                          — Entry point, wires components together
voice_assistant/
  audio_capture.py              — Mic input (pyaudio, 128-sample chunks)
  vad.py                        — Voice activity detection (Silero VAD)
  wake_word.py                  — Wake word detection (openWakeWord, alexa model)
  ring_buffer.py                — Circular audio buffer (numpy)
  orchestrator.py               — State machine, core control logic
  stt.py                        — Speech-to-text (OpenAI Whisper API, swappable via Protocol)
  ai_agent.py                   — AI chat agent (Claude via Vertex AI, swappable via Protocol)
  tts.py                        — Text-to-speech (OpenAI TTS, streaming PCM via PyAudio)
  audio_playback.py             — System audio output (afplay on macOS, greeting only)
  debug_utils.py                — Save captured audio as .wav
```

## Key Dependencies

- `openwakeword` — wake word detection (uses ONNX models from `resources/models/`)
- `silero-vad` — voice activity detection (via torch)
- `pyaudio` — mic capture and TTS audio output
- `numpy` — audio buffers
- `openai` — speech-to-text (Whisper API) and text-to-speech (TTS API)
- `anthropic[vertex]` — AI chat agent (Claude via Google Vertex AI)

## Environment Variables

- `OPENAI_API_KEY` — Required for Whisper STT and TTS
- `CLOUD_ML_REGION` — Vertex AI region (default: `us-east5`)
- `ANTHROPIC_VERTEX_PROJECT_ID` — Google Cloud project ID for Vertex AI
- `CLAUDE_MODEL` — Claude model ID (default: `claude-sonnet-4-6`)
- `CLAUDE_MAX_TOKENS` — Max response tokens (default: `1024`)
- `TTS_MODEL` — OpenAI TTS model (default: `tts-1`)
- `TTS_VOICE` — OpenAI TTS voice (default: `alloy`)

## Notes

- Wake word model: alexa_v0.1.onnx (downloaded via `openwakeword.utils.download_models()`)
- The installed openwakeword version uses `models` (lowercase) not `MODELS`, and `wakeword_model_paths` not `wakeword_models`
- macOS audio playback via `afplay` (built-in, greeting only)
- STT, AI agent, and TTS are all swappable via `typing.Protocol` — change one line in `run.py`
- TTS streams raw PCM audio (24kHz, 16-bit, mono) directly to PyAudio — no temp files
