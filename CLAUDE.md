# Voice Assistant

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
- `01_state_machine.md` — State machine: IDLE → LISTENING → WAITING_FOR_USER → CAPTURING
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
  audio_playback.py             — System audio output (afplay on macOS)
  debug_utils.py                — Save captured audio as .wav
```

## Key Dependencies

- `openwakeword` — wake word detection (uses ONNX models from `resources/models/`)
- `silero-vad` — voice activity detection (via torch)
- `pyaudio` — mic capture
- `numpy` — audio buffers

## Notes

- Wake word model: alexa_v0.1.onnx (downloaded via `openwakeword.utils.download_models()`)
- The installed openwakeword version uses `models` (lowercase) not `MODELS`, and `wakeword_model_paths` not `wakeword_models`
- macOS audio playback via `afplay` (built-in, no extra deps)
