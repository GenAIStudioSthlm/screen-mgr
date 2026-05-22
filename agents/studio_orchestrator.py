"""Studio orchestrator — routes a user message to the right specialist.

In Phase 3 the only domain wired up is Lighting. The orchestrator owns the
user-facing conversation; specialists own their domains. The orchestrator
does NOT call MCP tools directly — its "tools" are local Python dispatches
to other agents.

CLI smoke test:
    python -m agents.studio_orchestrator "warm up the studio for a meeting"
    python -m agents.studio_orchestrator "hi, what can you do?"
    python -m agents.studio_orchestrator "make it bright in there"   # ambiguous → ask_user
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Awaitable, Callable

from anthropic import Anthropic

from agents.lighting_specialist import build_lighting_specialist


# A local tool handler: receives the tool input dict and returns the
# text payload to hand back to the model as a tool_result.
ToolHandler = Callable[[dict], Awaitable[str]]


SYSTEM_PROMPT = """You are the Studio orchestrator — the operator-facing
agent for the Studio's control system.

You route the operator's natural-language requests to the right
specialist. Today you have one specialist available:

- **Lighting** (Philips Hue, Studio + Maker rooms). Use
  `delegate_to_lighting` for anything about lights, brightness, color,
  rooms, scenes, "presentation mode", "blackout", "wake up", etc.

If a request is clearly lighting-related, call `delegate_to_lighting`
with a focused brief that captures the operator's intent in one or two
sentences. Then summarise the specialist's reply for the operator in
one short line.

If a request is ambiguous (e.g. "make it bright in there" — which room?
how bright?), call `ask_user` with a single concise clarifying
question instead of guessing.

If a request is **not** about any domain you control (greetings, chit
chat, questions about what you can do), reply directly in plain text
without calling any tool. Keep replies short.

Never invent specialists or tools that aren't listed above. If the
operator asks for screens or LEDs, tell them those specialists aren't
wired up yet."""


TOOLS_SPEC = [
    {
        "name": "delegate_to_lighting",
        "description": (
            "Hand off a lighting-related request to the Lighting "
            "specialist. The specialist controls Philips Hue lights, "
            "groups, and scenes for the Studio. Pass a concise brief "
            "capturing what the operator wants — the specialist will "
            "translate it into Hue actions and report back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brief": {
                    "type": "string",
                    "description": (
                        "One or two sentences capturing the operator's "
                        "lighting intent. Include room name(s) if known."
                    ),
                }
            },
            "required": ["brief"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the operator a single clarifying question. Use only "
            "when a request is ambiguous and you can't safely pick a "
            "default. Don't use for chit-chat — reply in plain text "
            "for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "One short question for the operator.",
                }
            },
            "required": ["question"],
        },
    },
]


class Orchestrator:
    """Anthropic tool-use loop with local Python tool dispatch.

    Mirrors the shape of `agents.base.Specialist` but skips the MCP
    session — orchestrator tools are in-process delegations, not MCP
    calls. We keep this as a sibling class instead of forcing a common
    base; the two share a couple of helpers and that's it.
    """

    def __init__(
        self,
        name: str = "studio",
        system_prompt: str = SYSTEM_PROMPT,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
        max_iterations: int = 8,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self._anthropic = Anthropic()
        self._handlers: dict[str, ToolHandler] = {
            "delegate_to_lighting": self._handle_delegate_lighting,
            "ask_user": self._handle_ask_user,
        }
        # Questions raised via ask_user during the most recent run.
        # Phase 4's chat UI will read these to render a question chip;
        # in CLI mode we print them after the loop ends.
        self.pending_questions: list[str] = []

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def ask(self, user_msg: str) -> str:
        self.pending_questions = []
        messages: list[dict] = [{"role": "user", "content": user_msg}]
        messages = await self.converse(messages)
        return self._extract_text(messages[-1])

    async def converse(self, messages: list[dict]) -> list[dict]:
        for _ in range(self.max_iterations):
            resp = await asyncio.to_thread(
                self._anthropic.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=messages,
                tools=TOOLS_SPEC,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": [self._block_to_dict(b) for b in resp.content],
                }
            )

            if resp.stop_reason != "tool_use":
                return messages

            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                text, is_error = await self._dispatch(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": text,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        messages.append(
            {
                "role": "user",
                "content": (
                    f"[orchestrator {self.name}: hit max_iterations="
                    f"{self.max_iterations} without stop_reason=end_turn]"
                ),
            }
        )
        return messages

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _dispatch(self, name: str, args: dict) -> tuple[str, bool]:
        handler = self._handlers.get(name)
        if handler is None:
            return (f"unknown tool: {name!r}", True)
        try:
            text = await handler(args or {})
            return (text, False)
        except Exception as e:  # noqa: BLE001 — surface to model
            return (f"tool dispatch failed: {e!r}", True)

    async def _handle_delegate_lighting(self, args: dict) -> str:
        brief = (args.get("brief") or "").strip()
        if not brief:
            return "delegate_to_lighting requires a non-empty 'brief'."
        # Build a fresh specialist per delegation. Cheap on LAN, and
        # keeps each delegation a clean sub-conversation (no leaked
        # state between unrelated requests).
        specialist = build_lighting_specialist()
        return await specialist.ask(brief)

    async def _handle_ask_user(self, args: dict) -> str:
        question = (args.get("question") or "").strip()
        if not question:
            return "ask_user requires a non-empty 'question'."
        self.pending_questions.append(question)
        # The tool_result tells the model the question has been handed
        # off — it should now stop and wait for the next user turn.
        return "(question delivered to operator; awaiting their reply)"

    # ------------------------------------------------------------------
    # Helpers (small, duplicated from Specialist on purpose — see class
    # docstring; refactor only if a third caller shows up).
    # ------------------------------------------------------------------

    @staticmethod
    def _block_to_dict(block: Any) -> dict:
        if hasattr(block, "model_dump"):
            return block.model_dump()
        return json.loads(json.dumps(block, default=lambda o: o.__dict__))

    @staticmethod
    def _extract_text(message: dict) -> str:
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


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

async def _cli() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m agents.studio_orchestrator <prompt>")
        return 1
    user_msg = " ".join(sys.argv[1:])
    orch = Orchestrator()
    response = await orch.ask(user_msg)
    # Surface any clarifying questions before the final assistant text.
    for q in orch.pending_questions:
        print(f"[ask_user] {q}")
    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli()))
