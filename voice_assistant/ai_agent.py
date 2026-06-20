from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

log = logging.getLogger("ai_agent")

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@runtime_checkable
class ChatAgent(Protocol):
    def respond(self, user_message: str) -> str: ...


class ClaudeChat:
    def __init__(
        self,
        region: str | None = None,
        project_id: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        system: str = "You are a helpful voice assistant. Keep responses concise and conversational.",
    ):
        from anthropic import AnthropicVertex

        region = region or os.environ.get("CLOUD_ML_REGION", "us-east5")
        project_id = project_id or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
        model = model or os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
        max_tokens = max_tokens or int(os.environ.get("CLAUDE_MAX_TOKENS", "1024"))

        self._client = AnthropicVertex(region=region, project_id=project_id)
        self._model = model
        self._max_tokens = max_tokens
        self._system = system
        self._history: list[dict[str, str]] = []

    def respond(self, user_message: str) -> str:
        self._history.append({"role": "user", "content": user_message})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system,
            messages=self._history,
        )

        assistant_text = ""
        for block in response.content:
            if block.type == "text":
                assistant_text += block.text

        self._history.append({"role": "assistant", "content": assistant_text})
        return assistant_text

    def stream(
        self, user_message: str, interrupt: threading.Event | None = None
    ) -> Iterator[str]:
        self._history.append({"role": "user", "content": user_message})
        log.info("Streaming started")
        t0 = time.monotonic()

        full_response = ""
        buffer = ""

        with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system,
            messages=self._history,
        ) as response:
            for text in response.text_stream:
                if interrupt and interrupt.is_set():
                    break
                buffer += text
                while True:
                    match = SENTENCE_END.search(buffer)
                    if not match:
                        break
                    sentence = buffer[: match.start() + 1].strip()
                    buffer = buffer[match.end() :]
                    if sentence:
                        full_response += sentence + " "
                        log.info("Sentence at %.2fs: %s", time.monotonic() - t0, sentence)
                        yield sentence

        remaining = buffer.strip()
        if remaining and not (interrupt and interrupt.is_set()):
            full_response += remaining
            log.info("Final sentence at %.2fs: %s", time.monotonic() - t0, remaining)
            yield remaining

        log.info("Streaming done in %.2fs", time.monotonic() - t0)
        if full_response.strip():
            self._history.append({"role": "assistant", "content": full_response.strip()})
