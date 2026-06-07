# Voice Assistant — Audio Signal Flow

## Audio Formats

```
Mic output:       int16 PCM, 16kHz, mono, 128 samples per chunk (~8ms)
Ring buffer:      int16, circular numpy array, capacity configurable (currently 10s)
VAD (Silero):     needs float32 normalized [-1.0, 1.0], 512-sample frames
                  Conversion: int16 → float32 / 32768.0 (done in vad.py)
Wake word (OWW):  int16, 1280-sample chunks (80ms at 16kHz)
                  Accumulates internally, predicts per chunk
Captured audio:   list of int16 numpy arrays → concatenated for .wav export
```

## Signal Path Per Chunk

```
Mic hardware
  │
  ▼
AudioCapture.read(128 samples)     ← blocks ~8ms
  │
  ├──→ RingBuffer.write(chunk)     ← always, every chunk
  │
  ├──→ VAD.process(chunk)          ← accumulates 4 chunks (512 samples)
  │      │                            returns None until 512 accumulated
  │      ▼
  │    VADResult or None
  │
  └──→ event_queue.put((vad_result, chunk))
         │
         ▼
       Orchestrator.on_audio(vad_result, chunk)
         │
         ├── IDLE:     count VAD speech frames only (ignore chunk)
         ├── LISTENING: feed chunk to wake word (every chunk!)
         ├── WAITING:  count VAD speech frames only
         └── CAPTURING: append chunk to recording
```

## Ring Buffer Detail

```
Numpy circular buffer: pre-allocated int16 array.
Write pointer advances and wraps. Zero allocation after init.

write(chunk):
    remaining = capacity - write_ptr
    if remaining >= len(chunk):
        buffer[write_ptr : write_ptr + len(chunk)] = chunk
    else:
        buffer[write_ptr:] = chunk[:remaining]
        buffer[:len(chunk) - remaining] = chunk[remaining:]
    write_ptr = (write_ptr + len(chunk)) % capacity

read_last(ms):
    n = sample_rate * ms / 1000
    start = (write_ptr - n) % capacity
    if start < write_ptr:
        return buffer[start:write_ptr].copy()
    else:
        return concat(buffer[start:], buffer[:write_ptr])
```

## VAD Frame Accumulation

```
Silero VAD needs 512 samples at 16kHz (32ms).
AudioCapture delivers 128 samples (8ms).
VAD accumulates 4 chunks before running inference.

Chunk 1 (128) → accumulator [128]  → None
Chunk 2 (128) → accumulator [256]  → None
Chunk 3 (128) → accumulator [384]  → None
Chunk 4 (128) → accumulator [512]  → VADResult(is_speech, confidence)
                 accumulator reset

This means: one VAD decision every 32ms.
Orchestrator gets 4 chunks per VAD result (3 with None, 1 with result).
```

## Wake Word Accumulation

```
openWakeWord expects 1280 samples (80ms at 16kHz).
In LISTENING state, chunks arrive at 128 samples each.
Wake word accumulator fills across ~10 chunks before running inference.

Each predict() call updates an internal prediction buffer (rolling window).
The model is a streaming detector — it builds features across many frames.
A wake phrase like "hey alexa" (~3 seconds) spans many predict() calls.
The score ramps up as the phrase completes.
Threshold: 0.5 (default).
```
