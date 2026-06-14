# Voice Assistant — State Machine

## States

```
IDLE → LISTENING → WAITING_FOR_USER → CAPTURING → PROCESSING → WAITING_FOR_USER (loop)
```

```mermaid
stateDiagram-v2
    direction TB
    [*] --> IDLE

    state IDLE {
        note right of IDLE
            VAD: counting consecutive speech frames.
            Wake word model is OFF (saves compute).
            Transition: N consecutive speech frames → LISTENING
        end note
    }

    state LISTENING {
        note right of LISTENING
            On entry: replay last 2s from ring buffer through wake word model.
            Then: feed each live chunk to wake word.
            VAD: tracks consecutive silence for timeout.
            Transition (success): wake word detected → play greeting → WAITING_FOR_USER
            Transition (timeout): M consecutive silence frames → reset wake word → IDLE
        end note
    }

    state WAITING_FOR_USER {
        note right of WAITING_FOR_USER
            Playback guard: ignores all audio while greeting plays.
            VAD: counting consecutive speech frames.
            Transition: N consecutive speech frames → grab lookback → CAPTURING
            Transition: timeout (10s no speech) → IDLE
        end note
    }

    state CAPTURING {
        note right of CAPTURING
            Recording: ring buffer lookback + all live chunks.
            VAD: watching for sustained silence.
            Transition: 1.5s continuous silence → hand off recording → PROCESSING
        end note
    }

    state PROCESSING {
        note right of PROCESSING
            Thread 4 runs the pipeline: STT → Claude → TTS.
            This handler keeps listening for wake word (interrupt).
            Same lookback-then-realtime pattern as LISTENING.
            Transition (done): pipeline finishes → WAITING_FOR_USER
            Transition (interrupt): wake word detected → set interrupt → WAITING_FOR_USER
        end note
    }

    IDLE --> LISTENING : VAD confirms speech (consecutive frames)
    LISTENING --> WAITING_FOR_USER : wake word detected
    LISTENING --> IDLE : silence timeout
    WAITING_FOR_USER --> CAPTURING : VAD confirms speech
    WAITING_FOR_USER --> IDLE : 10s timeout
    CAPTURING --> PROCESSING : 1.5s silence → spawn processing thread
    PROCESSING --> WAITING_FOR_USER : pipeline done (multi-turn)
    PROCESSING --> WAITING_FOR_USER : wake word interrupt
```

## Key Design Decisions

### VAD-gated wake word (not always-on)
Wake word model only runs after VAD confirms speech. Saves compute
and avoids false triggers from background noise. Trade-off: adds
~320ms latency before wake word processing starts. The ring buffer
lookback recovers the audio from before VAD confirmed.

### Lookback-then-realtime
When entering LISTENING or PROCESSING, the handler first replays
recent audio from the ring buffer through the wake word model, then
switches to scanning live chunks. This recovers wake words that
started before the state transition happened.

### Playback guard (not AEC)
When system plays audio (greeting), all audio processing is paused
for the duration. Simple and effective for short clips. No echo
cancellation needed.

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
SILENCE_TIMEOUT_S = 3         # silence duration to finalize capture
IDLE_TIMEOUT_S = 10.0         # timeout in WAITING_FOR_USER
```
