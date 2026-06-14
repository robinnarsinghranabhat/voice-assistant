# Voice Assistant — Sequences

## Happy Path: Wake Word → Question → Response

User says "hey alexa", system acknowledges, user asks a question, assistant responds.

```
Time    Event                                   State           Thread
─────   ─────                                   ─────           ──────
0ms     User starts saying "hey alexa"          IDLE            T1: mic capture
        Audio chunks written to ring buffer                     T2: orchestrator counting
        VAD starts detecting speech                                  speech frames

~320ms  VAD: 10 consecutive speech frames       → LISTENING     T2: replays 2s lookback
        Ring buffer lookback (2s) fed to                             from ring buffer
        wake word model in 1280-sample chunks                        through wake word

~800ms  Wake word: "alexa" detected!            → WAITING       T3: spawns afplay
        Greeting audio plays (hello.mp3)                             for greeting
        Playback guard active (~duration)

~2.5s   Greeting finishes, guard expires        WAITING         T2: counting speech
        System now listening for user speech                         frames again

~4s     User starts speaking question           WAITING
        VAD detects speech, counting frames

~4.6s   20 consecutive speech frames            → CAPTURING     T2: appending chunks
        Ring buffer lookback (500ms) captured                        to recording
        Live chunks appended to recording

~8s     User stops speaking                     CAPTURING
        VAD detects silence

~11s    3s continuous silence                   → PROCESSING    T4: spawned
        Recording handed to processing thread                   T4: STT API call (~1-3s)
                                                                T1+T2: still running
                                                                (mic + orchestrator)

~13s    STT returns transcription               PROCESSING      T4: Claude streaming
        Claude starts streaming response                        T2: listening for
                                                                     wake word (interrupt)

~14s    First sentence ready                    PROCESSING      T4: TTS streams audio
        TTS speaks it while Claude continues                         to speaker

~18s    Claude done, last sentence spoken        → WAITING      T4: dies
        System ready for follow-up question                     T2: counting speech
                                                                     frames again
```

## Interrupt: Wake Word During Processing

User says "alexa" while the assistant is mid-response.

```
Time    Event                                   State           Thread
─────   ─────                                   ─────           ──────
0ms     Assistant is speaking (TTS active)      PROCESSING      T4: TTS streaming
        Mic still capturing, orchestrator                       T1+T2: still running
        still processing chunks

~0ms    User says "alexa"                       PROCESSING      T1: captures audio
        VAD detects speech on Thread 2                          T2: enters lookback-
                                                                     then-realtime

~400ms  Wake word detected in lookback          PROCESSING      T2: sets interrupt Event
        or live chunks                           → WAITING      T4: checks Event,
        interrupt Event set                                          stops TTS mid-sentence,
                                                                     exits

~1s     System ready for new question           WAITING         T2: counting speech
                                                                     frames again
```

## What the Ring Buffer Preserves

```
        User starts          VAD confirms        Wake word
        speaking             speech (10 frames)  processes lookback
        ↓                    ↓                   ↓
Audio:  [====hey alexa=======|===================|→ live chunks...]
        ↑                                        ↑
        This part is in the ring buffer           Lookback reads it
        BEFORE VAD triggers                       and feeds to wake word
```

Same pattern for WAITING → CAPTURING: the start of the user's
question is in the ring buffer before VAD confirms speech.

Same pattern again for interrupt during PROCESSING: the wake word
was spoken before the orchestrator started looking for it.
