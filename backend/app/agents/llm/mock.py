"""Deterministic mock LLM for tests and offline demo.

Behaviour: simple keyword routing. Real value is in test reproducibility -- the
runtime can be exercised end-to-end without network calls or API keys.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agents.llm.base import (
    LLMClient,
    StreamEvent,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    TurnEnd,
)


class MockLLMClient(LLMClient):
    """Pattern-matches keywords in the latest user message and emits a scripted response.

    Routing rules (in priority order):
      1. If the last message is a tool result, emit a short summary and end the turn.
      2. If user mentions "lead", call create_lead with extracted name/company.
      3. If user mentions "find" + "contact", call find_contact.
      4. If user mentions "opportunity" + "advance" or "stage", call advance_opportunity_stage.
      5. If user mentions "search" or "knowledge", call search_knowledge_base.
      6. Otherwise, plain text response.
    """

    def __init__(self, stream_delay_ms: float = 8.0):
        self.stream_delay_ms = stream_delay_ms

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
    ) -> AsyncIterator[StreamEvent]:
        last = messages[-1] if messages else {"role": "user", "content": ""}
        tool_names = {t.name for t in tools}

        # Case 1: synthesizing on top of a tool result
        if last.get("role") == "tool":
            content = str(last.get("content", ""))
            preview = content[:120].replace("\n", " ")
            text = f"Done. Result: {preview}"
            async for ev in self._emit_text(text):
                yield ev
            yield TurnEnd(stop_reason="end_turn", tokens_in=len(content) // 4, tokens_out=len(text) // 4)
            return

        user_text = self._latest_user_text(messages).lower()

        # Case 2: lead creation
        if "lead" in user_text and "create_lead" in tool_names:
            name_match = re.search(r"(?:for|named)\s+([A-Z][a-z]+ [A-Z][a-z]+)", self._latest_user_text(messages))
            company_match = re.search(r"(?:at|from)\s+([A-Z][\w& ]+)", self._latest_user_text(messages))
            first, last_name = ("Jane", "Doe")
            if name_match:
                parts = name_match.group(1).split(" ", 1)
                first, last_name = parts[0], parts[1] if len(parts) > 1 else "Doe"
            company = company_match.group(1).strip() if company_match else "Acme Corp"
            preface = "I'll create that lead now."
            async for ev in self._emit_text(preface):
                yield ev
            yield ToolCallRequest(
                call_id=f"call_{uuid.uuid4().hex[:8]}",
                name="create_lead",
                arguments={"first_name": first, "last_name": last_name, "company": company},
            )
            yield TurnEnd(stop_reason="tool_use", tokens_in=64, tokens_out=32)
            return

        # Case 3: find contact
        if "find" in user_text and "contact" in user_text and "find_contact" in tool_names:
            email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", self._latest_user_text(messages))
            args: dict[str, Any] = {}
            if email_match:
                args["email"] = email_match.group(0)
            else:
                args["query"] = self._latest_user_text(messages)
            async for ev in self._emit_text("Looking that up."):
                yield ev
            yield ToolCallRequest(call_id=f"call_{uuid.uuid4().hex[:8]}", name="find_contact", arguments=args)
            yield TurnEnd(stop_reason="tool_use", tokens_in=48, tokens_out=16)
            return

        # Case 4: advance opportunity
        if "opportunity" in user_text and ("advance" in user_text or "stage" in user_text):
            if "advance_opportunity_stage" in tool_names:
                async for ev in self._emit_text("Advancing the opportunity."):
                    yield ev
                yield ToolCallRequest(
                    call_id=f"call_{uuid.uuid4().hex[:8]}",
                    name="advance_opportunity_stage",
                    arguments={"query": self._latest_user_text(messages)},
                )
                yield TurnEnd(stop_reason="tool_use", tokens_in=48, tokens_out=16)
                return

        # Case 5: knowledge search
        if ("search" in user_text or "knowledge" in user_text) and "search_knowledge_base" in tool_names:
            async for ev in self._emit_text("Searching the knowledge base."):
                yield ev
            yield ToolCallRequest(
                call_id=f"call_{uuid.uuid4().hex[:8]}",
                name="search_knowledge_base",
                arguments={"query": self._latest_user_text(messages)},
            )
            yield TurnEnd(stop_reason="tool_use", tokens_in=48, tokens_out=16)
            return

        # Default: plain text answer
        text = (
            "I'm an AgentForge agent. I can create leads, find contacts, advance opportunities, "
            "and search the knowledge base. What would you like to do?"
        )
        async for ev in self._emit_text(text):
            yield ev
        yield TurnEnd(stop_reason="end_turn", tokens_in=64, tokens_out=len(text) // 4)

    async def _emit_text(self, text: str) -> AsyncIterator[TextDelta]:
        # Stream word-by-word for realistic UX
        for word in text.split(" "):
            yield TextDelta(text=word + " ")
            await asyncio.sleep(self.stream_delay_ms / 1000.0)

    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                # list-of-blocks form
                return " ".join(b.get("text", "") for b in content if b.get("type") == "text")
        return ""
