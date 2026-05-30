"""Anthropic SDK client configured for MiniMax."""
from __future__ import annotations

import os
from typing import Any, AsyncIterator, Iterator

from anthropic import Anthropic, AsyncAnthropic

from draguniteus.config import Config


class DraguniteusClient:
    """Wrapper around Anthropic SDK with MiniMax base URL and tool-calling support."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._sync = Anthropic(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        self._async: AsyncAnthropic | None = None

    @property
    def sync(self) -> Anthropic:
        return self._sync

    @property
    def async_client(self) -> AsyncAnthropic:
        if self._async is None:
            self._async = AsyncAnthropic(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
            )
        return self._async

    # -------------------------------------------------------------------------
    # Tool schemas
    # -------------------------------------------------------------------------

    @staticmethod
    def get_tool_schemas() -> list[dict[str, Any]]:
        """Return all tool definitions in Anthropic function-calling format."""
        from draguniteus.tools import ALL_TOOLS
        from draguniteus.tools.mcp_tools import build_mcp_tool_schemas
        return ALL_TOOLS + build_mcp_tool_schemas()

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
        system: str | None = None,
        betas: list[str] | None = None,
    ) -> Iterator[Any]:
        """Stream a message creation with full event iterator.

        Yields raw SDK events. Upstream code handles content_block_delta,
        thinking_delta, tool_use_delta, etc.
        """
        m = model or self.config.model
        mt = max_tokens or self.config.max_tokens
        temp = temperature if temperature is not None else self.config.temperature

        kwargs: dict[str, Any] = {
            "model": str(m),
            "messages": messages,
            "stream": True,
            "max_tokens": int(mt),
            "temperature": float(temp),
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = str(system)
        # NOTE: betas parameter is accepted for compatibility but NOT passed to API
        # MiniMax API does not support the betas parameter

        import copy
        import json
        # WORKAROUND: Serialize + deserialize to strip any typing wrappers,
        # ArgumentInfo objects, or other non-JSON-serializable types that may
        # have leaked in during module initialization.
        if "tools" in kwargs:
            kwargs["tools"] = json.loads(json.dumps(kwargs["tools"]))
        if "messages" in kwargs:
            kwargs["messages"] = json.loads(json.dumps(kwargs["messages"]))
        if "system" in kwargs and kwargs["system"]:
            kwargs["system"] = str(kwargs["system"])

        return self._sync.messages.create(**kwargs)

    def create(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[dict] | None = None,
        system: str | None = None,
        betas: list[str] | None = None,
    ) -> Any:
        """Non-streaming message creation."""
        kwargs: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = system
        # NOTE: betas parameter is accepted for compatibility but NOT passed to API
        # MiniMax API does not support the betas parameter

        return self._sync.messages.create(**kwargs)

    # -------------------------------------------------------------------------
    # Token counting
    # -------------------------------------------------------------------------

    def count_tokens(self, messages: list[dict], model: str | None = None) -> int:
        """Return input token count for a message list."""
        result = self._sync.messages.count_tokens(
            model=model or self.config.model,
            messages=messages,
        )
        return result.input_tokens

    # -------------------------------------------------------------------------
    # Builder
    # -------------------------------------------------------------------------

    def with_options(self, **kwargs: Any) -> DraguniteusClient:
        """Return a new client with per-request overrides."""
        new = DraguniteusClient(self.config)
        # Preserve overridden config values
        for k, v in kwargs.items():
            setattr(new.config, k, v)
        return new