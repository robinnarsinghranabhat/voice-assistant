# Voice Assistant — State Machine

## Current Implementation

```
IDLE → LISTENING → WAITING_FOR_USER → CAPTURING → IDLE
```

```mermaid
stateDiagram-v2
    direction TB
    [*] --> IDLE

    state IDLE {
        note right of IDLE
            Ring Buffer: always writing (all mic chunks)
            VAD: running, counting consecutive speech frames
            Wake Word: inactive (saves compute)
            Transition: N consecutive VAD speech frames → LISTENING
        end note
    }

    state LISTENING {
        note right of LISTENING
            On entry: feed ring buffer lookback to wake word model
            Then: feed every incoming audio chunk to wake word
            VAD: tracks consecutive silence for timeout
            Transition (success): wake word detected → play greeting → WAITING_FOR_USER
            Transition (timeout): M consecutive silence frames → reset wake word → IDLE
        end note
    }

    state WAITING_FOR_USER {
        note right of WAITING_FOR_USER
            Playback guard: ignores all audio while greeting plays
            VAD: counting consecutive speech frames
            Transition: N consecutive speech frames → grab lookback → CAPTURING
            Transition: timeout (10s no speech) → IDLE
        end note
    }

    state CAPTURING {
        note right of CAPTURING
            Recording: ring buffer lookback + all live chunks
            VAD: watching for sustained silence
            Transition: 1.5s continuous silence → finalize recording → IDLE
            Debug mode: saves captured audio as .wav
        end note
    }

    IDLE --> LISTENING : VAD confirms speech (consecutive frames)
    LISTENING --> WAITING_FOR_USER : wake word detected
    LISTENING --> IDLE : silence timeout
    WAITING_FOR_USER --> CAPTURING : VAD confirms speech
    WAITING_FOR_USER --> IDLE : 10s timeout
    CAPTURING --> IDLE : 1.5s silence
```

## Key Design Decisions

### VAD-gated wake word (not always-on)
Wake word model only runs after VAD confirms speech. Saves compute
and avoids false triggers from background noise. Trade-off: adds
~160-320ms latency before wake word processing starts. Lookback from
ring buffer recovers the audio from before VAD confirmed.

### Playback guard (not AEC)
When system plays audio (greeting), all audio processing is paused
for the duration. Simple and effective for short clips. No echo
cancellation needed for v1.

### Consecutive frame confirmation
Both IDLE→LISTENING and WAITING_FOR_USER→CAPTURING require multiple
consecutive VAD speech frames before transitioning. Prevents single
noisy frames from triggering state changes.

## Tunable Parameters

```
VAD_CONFIRM_FRAMES = 10       # consecutive speech frames to trigger LISTENING
WAKE_WORD_LOOKBACK_MS = 2000  # audio history fed to wake word on entry
SILENCE_RESET_FRAMES = 30     # consecutive silence frames to abandon LISTENING
CAPTURE_CONFIRM_FRAMES = 20   # consecutive speech frames to start CAPTURING
CAPTURE_LOOKBACK_MS = 500     # audio history prepended to recording
SILENCE_TIMEOUT_S = 1.5       # silence duration to finalize capture
IDLE_TIMEOUT_S = 10.0         # timeout in WAITING_FOR_USER
```

## Future: Full Pipeline States

When STT + LLM + TTS are added, the state machine extends:

```
CAPTURING → PROCESSING → RESPONDING → WAITING_FOR_USER (multi-turn)
                                    → IDLE (conversation done)

RESPONDING + user interrupt → INTERRUPTED → CAPTURING
```

PROCESSING: STT transcribes captured audio, sends to LLM.
RESPONDING: TTS plays LLM response. AEC may be needed here if we
want interrupt detection during playback (vs. simpler playback guard).
