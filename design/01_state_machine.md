# Voice Assistant — State Machine

Every detail matters: what VAD does in each state, what audio goes where,
what triggers transitions, and what happens to in-flight work on interrupts.

## Primary State Machine

```mermaid
stateDiagram-v2
    direction TB

    [*] --> IDLE

    state IDLE {
        direction LR
        note right of IDLE
            AEC: inactive (TTS not playing)
            Ring Buffer: always writing last 500ms
            VAD: running on raw mic chunks
            Wake Word: runs ONLY when VAD says "yes"
            Audio path: Mic → RingBuffer + VAD → [if yes] → WakeWord
        end note
    }

    state ACKNOWLEDGING {
        direction LR
        note right of ACKNOWLEDGING
            AEC: ACTIVE (TTS is playing "Go ahead")
            VAD: running on AEC-cleaned signal, but IGNORED
            Ring Buffer: writing AEC-cleaned audio
            TTS: playing short acknowledgment
            Purpose: give user feedback that system heard wake word
            Duration: ~500ms-1s
        end note
    }

    state WAITING_FOR_USER {
        direction LR
        note right of WAITING_FOR_USER
            AEC: inactive (TTS done)
            VAD: running on raw mic, ACTIVE — waiting for user to speak
            Ring Buffer: writing raw mic audio
            Key: first VAD "yes" triggers transition
            Timeout: if no speech for ~15s → back to IDLE
            Why ring buffer matters here: user may start
            speaking 200-300ms BEFORE VAD detects it.
            The ring buffer preserves that clipped beginning.
        end note
    }

    state CAPTURING {
        direction LR
        note right of CAPTURING
            AEC: inactive (TTS not playing)
            VAD: running — watching for SILENCE to know user stopped
            Recording: ring buffer lookback (last ~300ms) + live mic
            End condition: VAD says "no" for 1.5-2s continuously
            Edge case: user pauses mid-sentence for 1s to think.
            Too-short silence threshold = premature cutoff.
            Too-long = sluggish response. 1.5-2s is typical.
        end note
    }

    state PROCESSING {
        direction LR
        state "STT (Whisper)" as stt
        state "LLM (Claude)" as llm
        state "Tool Execution" as tools
        state "Response TTS" as tts_response

        stt --> llm : transcript text
        llm --> tools : tool calls (if any)
        tools --> llm : tool results
        llm --> tts_response : response text (streamed)

        note right of PROCESSING
            AEC: ACTIVE during tts_response sub-state
            VAD: running on AEC-cleaned signal during TTS
            Ring Buffer: writing AEC-cleaned audio during TTS
            
            During STT/LLM/Tools (no TTS playing):
              AEC inactive, VAD on raw mic
            During Response TTS:
              AEC active, VAD on cleaned signal
              VAD "yes" here = potential user interrupt
        end note
    }

    state INTERRUPTED {
        direction LR
        note right of INTERRUPTED
            TTS: stopped immediately
            AEC: transitions to inactive (TTS stopped)
            Current LLM/tool work: depends on sub-state
              - If mid-TTS: just stop speaking
              - If mid-tool-call: let it finish in background,
                but don't TTS the result
              - If mid-LLM: cancel the API call
            Then: treat interrupt audio as new utterance
            Ring buffer has the start of what user said
        end note
    }

    IDLE --> ACKNOWLEDGING : wake word confirmed
    ACKNOWLEDGING --> WAITING_FOR_USER : TTS playback done
    WAITING_FOR_USER --> IDLE : timeout (15s no speech)
    WAITING_FOR_USER --> CAPTURING : VAD detects speech
    CAPTURING --> PROCESSING : silence for ~2s (utterance complete)
    PROCESSING --> WAITING_FOR_USER : response done + multi-turn
    PROCESSING --> IDLE : response done + conversation over
    PROCESSING --> INTERRUPTED : VAD on cleaned signal during TTS
    INTERRUPTED --> CAPTURING : start capturing interrupt utterance
```

## What VAD Does in Every State (Summary Table)

```
┌──────────────────────┬──────────────┬─────────────────────────┬──────────────────────┐
│ State                │ AEC Active?  │ VAD Input               │ VAD Output Used For  │
├──────────────────────┼──────────────┼─────────────────────────┼──────────────────────┤
│ IDLE                 │ No           │ Raw mic                 │ Gate wake word model │
│ ACKNOWLEDGING        │ YES          │ AEC-cleaned signal      │ Ignored (AI talking) │
│ WAITING_FOR_USER     │ No           │ Raw mic                 │ Trigger capture      │
│ CAPTURING            │ No           │ Raw mic                 │ Detect end-of-speech │
│ PROCESSING (no TTS)  │ No           │ Raw mic                 │ Detect interrupt     │
│ PROCESSING (TTS)     │ YES          │ AEC-cleaned signal      │ Detect interrupt     │
│ INTERRUPTED          │ No (TTS off) │ Raw mic                 │ Continue to CAPTURING│
└──────────────────────┴──────────────┴─────────────────────────┴──────────────────────┘
```

## Edge Cases & Open Questions

1. **Multi-turn detection**: How does the LLM signal "I expect a follow-up" vs
   "conversation is done"? Options:
   - LLM explicitly returns a `expects_reply: bool` field
   - Default to multi-turn, timeout to IDLE after 15s silence
   - User says "thanks" or "that's all" → IDLE

2. **Overlapping tool calls**: If user asks "save this to Notion and email it to John",
   LLM may issue two tool calls. Both should run in parallel. If user interrupts
   mid-execution, do we cancel both? Let both finish? Cancel unfired ones only?
   Recommendation: let in-flight tool calls finish, cancel queued ones.

3. **Wake word vs interrupt**: In IDLE, we require wake word. In PROCESSING (during TTS),
   do we require wake word to interrupt, or just any speech? Trade-off:
   - Require wake word: more reliable, fewer false interrupts, slightly annoying
   - Any speech: natural UX, but false positives from ambient noise
   Recommendation for v1: require wake word to interrupt.

4. **Self-hearing during ACKNOWLEDGING**: The "Go ahead" TTS is short (~500ms).
   AEC handles it, but there's a brief window. If AEC isn't perfect, could
   "Go ahead" trigger VAD → wake word? Low risk (it's short), but worth noting.
