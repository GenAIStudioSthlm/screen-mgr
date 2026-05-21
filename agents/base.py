"""Specialist base class — Anthropic + MCP message loop.

A `Specialist` wraps one MCP server (by URL) + a system prompt. Each
`converse()` call opens an SSE session to the MCP server, lists tools,
and runs the standard Claude tool-use loop until the model stops
calling tools.

For Phase 2 the CLI smoke test exercises a single-turn `ask()`; later
phases (chat panel, room voice) call `converse()` with a growing
history of messages to maintain multi-turn context.

Connection lifecycle note: we open + close the MCP SSE session per
`converse()` call. Cheap on a LAN; revisit when the chat panel needs
to keep a session warm across many short turns.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from anthropic import Anthropic
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


class Specialist:
    def __init__(
        self,
        name: str,
        mcp_url: str,
        system_prompt: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        max_iterations: int = 12,
    ) -> None:
        self.name = name
        self.mcp_url = mcp_url
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        # Hard cap to avoid runaway tool loops if the model misbehaves.
        self.max_iterations = max_iterations
        self._anthropic = Anthropic()  # reads ANTHROPIC_API_KEY from env

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def ask(self, user_msg: str) -> str:
        """Single-turn convenience: send one user message, get the final
        assistant text back. Intermediate tool calls happen invisibly."""
        messages = [{"role": "user", "content": user_msg}]
        messages = await self.converse(messages)
        return self._extract_text(messages[-1])

    async def converse(self, messages: list[dict]) -> list[dict]:
        """Run the message loop until Claude stops requesting tools.
        Mutates and returns the messages list so callers can keep the
        conversation alive across turns."""
        async with sse_client(self.mcp_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_resp = await session.list_tools()
                tools = [self._tool_to_anthropic(t) for t in tools_resp.tools]

                for _ in range(self.max_iterations):
                    resp = await asyncio.to_thread(
                        self._anthropic.messages.create,
                        model=self.model,
                        max_tokens=self.max_tokens,
                        system=self.system_prompt,
                        messages=messages,
                        tools=tools,
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": [self._block_to_dict(b) for b in resp.content],
                        }
                    )

                    if resp.stop_reason != "tool_use":
                        return messages

                    # Dispatch every tool_use block back through MCP.
                    tool_results = []
                    for block in resp.content:
                        if block.type != "tool_use":
                            continue
                        text, is_error = await self._dispatch_tool(
                            session, block.name, block.input
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": text,
                                "is_error": is_error,
                            }
                        )
                    messages.append({"role": "user", "content": tool_results})

                # Loop cap hit — return what we have so the caller can see
                # the partial conversation and decide what to do.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"[specialist {self.name}: hit max_iterations="
                            f"{self.max_iterations} without stop_reason=end_turn]"
                        ),
                    }
                )
                return messages

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_to_anthropic(mcp_tool: Any) -> dict:
        """MCP tool object → Anthropic tool dict."""
        return {
            "name": mcp_tool.name,
            "description": mcp_tool.description or "",
            "input_schema": mcp_tool.inputSchema,
        }

    @staticmethod
    async def _dispatch_tool(
        session: ClientSession, name: str, args: dict
    ) -> tuple[str, bool]:
        """Call an MCP tool and return (text, is_error). MCP errors come
        back as a result with `isError=True`; transport exceptions become
        plain string errors we hand to Claude as a tool_result so it can
        recover instead of crashing the loop."""
        try:
            result = await session.call_tool(name, args)
        except Exception as e:  # noqa: BLE001 — surface any failure to the model
            return (f"tool dispatch failed: {e!r}", True)

        text_parts: list[str] = []
        for c in result.content or []:
            text = getattr(c, "text", None)
            text_parts.append(text if text is not None else str(c))
        text = "\n".join(text_parts) if text_parts else "(empty)"
        is_error = bool(getattr(result, "isError", False))
        return (text, is_error)

    @staticmethod
    def _block_to_dict(block: Any) -> dict:
        """Anthropic SDK content block → dict. We pass the dict form back
        into the next request so the SDK is happy with either input shape."""
        if hasattr(block, "model_dump"):
            return block.model_dump()
        # Fallback for plain objects.
        return json.loads(json.dumps(block, default=lambda o: o.__dict__))

    @staticmethod
    def _extract_text(message: dict) -> str:
        """Pull text content out of an assistant message dict."""
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        parts: list[str] = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif getattr(b, "type", None) == "text":
                parts.append(getattr(b, "text", ""))
        return "\n".join(p for p in parts if p).strip() or "(no text response)"
