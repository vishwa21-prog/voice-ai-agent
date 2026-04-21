"""
Agent Orchestrator
Drives the full reasoning loop: parse intent → select tool → execute → compose reply.
Uses Claude (Anthropic) as the LLM with structured tool-calling.
"""

import json
import logging
from typing import Any

import anthropic

from agent.tools.definitions import TOOL_DEFINITIONS
from agent.tools.executor import ToolExecutor
from agent.prompt.system_prompt import build_system_prompt
from memory.session import SessionMemory
from memory.persistent import PersistentMemory
from scheduler.appointment_engine import AppointmentEngine

logger = logging.getLogger("2care.agent")


GREETINGS = {
    "en": "Hello! I'm your 2Care appointment assistant. How can I help you today?",
    "hi": "नमस्ते! मैं आपका 2Care अपॉइंटमेंट सहायक हूँ। आज मैं आपकी कैसे मदद कर सकता हूँ?",
    "ta": "வணக்கம்! நான் உங்கள் 2Care சந்திப்பு உதவியாளர். இன்று நான் உங்களுக்கு எவ்வாறு உதவலாம்?",
}

RETURNING_GREETINGS = {
    "en": "Welcome back, {name}! How can I help you today?",
    "hi": "स्वागत है, {name}! आज मैं आपकी कैसे मदद कर सकता हूँ?",
    "ta": "மீண்டும் வரவேற்கிறோம், {name}! இன்று நான் உங்களுக்கு எவ்வாறு உதவலாம்?",
}


class AgentOrchestrator:
    def __init__(
        self,
        appointment_engine: AppointmentEngine,
        session_memory: SessionMemory,
        persistent_memory: PersistentMemory,
        session_id: str,
        patient_id: str,
    ):
        self.client = anthropic.Anthropic()
        self.appointment_engine = appointment_engine
        self.session_memory = session_memory
        self.persistent_memory = persistent_memory
        self.session_id = session_id
        self.patient_id = patient_id
        self.tool_executor = ToolExecutor(appointment_engine, patient_id)

    def get_greeting(self, language: str, profile: dict) -> str:
        name = profile.get("name")
        if name:
            template = RETURNING_GREETINGS.get(language, RETURNING_GREETINGS["en"])
            return template.format(name=name)
        return GREETINGS.get(language, GREETINGS["en"])

    async def process(self, user_message: str, language: str) -> tuple[str, list]:
        """
        Main agentic reasoning loop.
        Returns (response_text, reasoning_trace).
        """
        # Load context
        session_ctx = self.session_memory.get_context(self.session_id)
        patient_profile = self.persistent_memory.load_profile(self.patient_id)
        conversation_history = self.session_memory.get_history(self.session_id)

        system_prompt = build_system_prompt(language, patient_profile, session_ctx)

        # Append the new user message
        conversation_history.append({"role": "user", "content": user_message})

        reasoning_trace = []
        final_response = ""
        messages = list(conversation_history)

        # Agentic loop — keep going until the model stops calling tools
        while True:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Collect any text the model emitted before tool calls
            text_blocks = [b.text for b in response.content if b.type == "text" and b.text]

            if response.stop_reason == "tool_use":
                tool_calls = [b for b in response.content if b.type == "tool_use"]

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_input = tool_call.input

                    logger.info(f"🔧 Tool call: {tool_name}({json.dumps(tool_input)})")
                    reasoning_trace.append({
                        "step": "tool_call",
                        "tool": tool_name,
                        "input": tool_input,
                    })

                    tool_result = self.tool_executor.execute(tool_name, tool_input)
                    reasoning_trace.append({
                        "step": "tool_result",
                        "tool": tool_name,
                        "result": tool_result,
                    })

                    logger.info(f"📦 Tool result: {json.dumps(tool_result)}")

                    # Feed result back into the conversation
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_call.id,
                            "content": json.dumps(tool_result),
                        }],
                    })

            else:
                # Model is done — collect final text response
                final_response = " ".join(text_blocks).strip()
                if not final_response:
                    final_response = self._fallback(language)
                break

        # Persist updated history
        conversation_history.append({"role": "assistant", "content": final_response})
        self.session_memory.save_history(self.session_id, conversation_history)

        # Update session context with last detected intent (from trace)
        intent_steps = [t for t in reasoning_trace if t.get("tool") == "bookAppointment"]
        if intent_steps:
            self.session_memory.update_context(self.session_id, {"last_action": "booking"})

        return final_response, reasoning_trace

    def _fallback(self, language: str) -> str:
        fallbacks = {
            "en": "I'm sorry, I didn't quite catch that. Could you please repeat?",
            "hi": "माफ़ करें, मैं समझ नहीं पाया। क्या आप दोबारा बता सकते हैं?",
            "ta": "மன்னிக்கவும், எனக்கு புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
        }
        return fallbacks.get(language, fallbacks["en"])
