# Voice Assistant — Sequence (Happy Path)

## Current: Wake Word → Capture

User says "hey alexa", system acknowledges, user asks a question, audio is captured.

```
Time    Event                                   State
─────   ─────                                   ─────
0ms     User starts saying "hey alexa"          IDLE
        Audio chunks written to ring buffer
        VAD starts detecting speech

~320ms  VAD: 10 consecutive speech frames       IDLE → LISTENING
        Ring buffer lookback (2000ms) fed to
        wake word model in 1280-sample chunks

~400ms  Wake word model processes lookback      LISTENING
        + incoming live chunks

~800ms  Wake word: "alexa" detected!            LISTENING → WAITING_FOR_USER
        Greeting audio plays (hello.mp3)
        Playback guard active (~duration of clip)

~2.5s   Greeting finishes, guard expires        WAITING_FOR_USER
        System now listening for user speech

~4s     User starts speaking question           WAITING_FOR_USER
        VAD detects speech, counting frames

~4.6s   20 consecutive speech frames            WAITING_FOR_USER → CAPTURING
        Ring buffer lookback (500ms) captured
        Live chunks appended to recording

~8s     User stops speaking                     CAPTURING
        VAD detects silence

~9.5s   1.5s continuous silence                 CAPTURING → IDLE
        Recording finalized
        (Debug: saved as .wav)
        Total captured: ~5s of audio
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

Same pattern for WAITING_FOR_USER → CAPTURING: the start of the user's
question is in the ring buffer before VAD confirms speech.

## Playback Guard Timing

```
Wake word detected → play_audio(hello.mp3)
                     ↓
                     get_duration() → e.g., 1.8s
                     notify_playback_start(1.8)
                     ↓
                     _playback_guard_until = now + 1.8s
                     ↓
                     All on_audio() calls return early for 1.8s
                     ↓
                     Guard expires, WAITING_FOR_USER resumes
```
