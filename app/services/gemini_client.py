"""
Gemini client wrapper for advanced analytical responses based on Supabase data.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Mapping, Sequence

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiService:
    """
    Provides an interface to Google Gemini for data-driven answers.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        os.environ.setdefault("GEMINI_API_KEY", api_key)
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def answer_question(
        self,
        *,
        question: str,
        metrics: Mapping[str, Any],
        system_instruction: str | None = None,
        thinking_budget: int = 0,
        knowledge_sections: Sequence[Mapping[str, str]] | None = None,
        conversation_history: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        """
        Generate a response using Gemini with the provided metrics context.
        """

        def _call() -> str:
            # Build config without thinking_config to avoid validation errors
            # Thinking is enabled by default in Gemini 2.5 Flash/Pro models
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
                or (
                    "You are a data analyst and operations expert for a port operations team. "
                    "Answer in Hebrew, using the data provided in the JSON context and any knowledge base excerpts. "
                    "\n\n"
                    "WRITING STYLE GUIDELINES:\n"
                    "- Keep answers concise and focused - maximum 3-4 short paragraphs\n"
                    "- Use bullet points (•) sparingly, only for key information\n"
                    "- Start with a direct answer to the question\n"
                    "- Use clear, simple language - avoid unnecessary technical jargon\n"
                    "- For regulatory/operational questions: summarize main points, don't list every detail\n"
                    "- Highlight the most important information first\n"
                    "- Use bold (**text**) only for critical information\n"
                    "\n"
                    "IMPORTANT: If the question asks about dates, months, or time periods, "
                    "you MUST interpret and extract them from the question text, even if they "
                    "are written in Hebrew or with typos. For example:\n"
                    "- 'כמה מכולות נפרקו בפברואר 25' means 'how many containers were unloaded in February 2025'\n"
                    "- 'כמה מכולות בפבאור 25' means February 2025 (פבאור is a typo for פברואר)\n"
                    "- Hebrew month names: ינואר=January, פברואר=February, מרץ=March, אפריל=April, "
                    "מאי=May, יוני=June, יולי=July, אוגוסט=August, ספטמבר=September, "
                    "אוקטובר=October, נובמבר=November, דצמבר=December\n"
                    "- Years: '25' means 2025, '24' means 2024, etc.\n"
                    "\n"
                    "When answering questions about containers or vehicles:\n"
                    "- Look for date ranges in the 'period' field of the metrics\n"
                    "- Count containers from 'containers.daily_counts' or calculate from 'containers.total_records'\n"
                    "- For monthly queries, sum all containers in that month from 'containers.daily_counts'\n"
                    "- Always provide specific numbers when available\n"
                    "\n"
                    "For operational questions (e.g., procedures, regulations, port operations):\n"
                    "- Use information from knowledge base excerpts if provided\n"
                    "- If no relevant excerpts are provided, use your general knowledge about port operations\n"
                    "- Be specific and practical in your answers\n"
                    "- If you don't have enough information, state what is missing clearly\n"
                    "\n"
                    "If the context lacks information required to answer accurately, "
                    "state clearly what is missing instead of guessing."
                ),
                temperature=0.3,
            )
            prompt = self._build_prompt(
                question=question,
                metrics=metrics,
                knowledge_sections=knowledge_sections,
                conversation_history=conversation_history,
            )
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            return (response.text or "").strip()

        return await asyncio.to_thread(_call)

    @staticmethod
    def _build_prompt(
        *,
        question: str,
        metrics: Mapping[str, Any],
        knowledge_sections: Sequence[Mapping[str, str]] | None = None,
        conversation_history: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        context = json.dumps(metrics, ensure_ascii=False, indent=2)
        parts = [
            "Contextual data (JSON):",
            context,
        ]
        
        # Add conversation history if available
        if conversation_history:
            parts.append("\nPrevious conversation context:")
            for idx, hist_item in enumerate(conversation_history, start=1):
                user_q = hist_item.get("user_text", "")
                bot_a = hist_item.get("response_text", "")
                if user_q or bot_a:
                    parts.append(f"\n[Previous exchange {idx}]:")
                    if user_q:
                        parts.append(f"User: {user_q}")
                    if bot_a:
                        # Truncate long responses to avoid token limits
                        truncated = bot_a[:200] + "..." if len(bot_a) > 200 else bot_a
                        parts.append(f"Bot: {truncated}")
            parts.append("\n---")
        if knowledge_sections:
            parts.append("Relevant knowledge base excerpts:")
            for index, section in enumerate(knowledge_sections, start=1):
                # Support both hazard documents (document_title/document_id) and topic knowledge (topic)
                title = (
                    section.get("document_title")
                    or section.get("topic")
                    or section.get("document_id")
                    or f"Section {index}"
                )
                source = section.get("source_file", "document")
                excerpt = section.get("excerpt", "").strip()
                identifier = section.get("section_id", f"{index}")
                if not excerpt:
                    continue
                parts.append(
                    f"[{index}] {title} ({source}, id={identifier}):\n{excerpt}"
                )
        parts.append("Using only the context above, answer the following question:")
        parts.append(question)
        parts.append(
            "\n"
            "CRITICAL INSTRUCTIONS:\n"
            "\n"
            "WRITING STYLE - Keep your answer concise and clear:\n"
            "- Maximum 3-4 short paragraphs\n"
            "- Start with a direct, clear answer\n"
            "- Use bullet points only for key information (max 3-4 bullets)\n"
            "- Summarize main points, don't list every detail\n"
            "- Use simple, professional language\n"
            "\n"
            "1. DATE INTERPRETATION:\n"
            "   - Extract month names and years from the question, even with typos\n"
            "   - Hebrew months: ינואר=01, פברואר=02, מרץ=03, אפריל=04, מאי=05, יוני=06, "
            "יולי=07, אוגוסט=08, ספטמבר=09, אוקטובר=10, נובמבר=11, דצמבר=12\n"
            "   - Common typos: 'פבאור' or 'פבואר' = פברואר (February)\n"
            "   - Years: '25' = 2025, '24' = 2024, etc.\n"
            "\n"
            "2. DATA FORMAT:\n"
            "   - Dates in 'containers.daily_counts' are in YYYYMMDD format (e.g., '20250215' = Feb 15, 2025)\n"
            "   - To find February 2025, look for keys starting with '202502' (2025-02-XX)\n"
            "   - To find January 2024, look for keys starting with '202401' (2024-01-XX)\n"
            "\n"
            "3. CALCULATION:\n"
            "   - For monthly queries: Sum ALL values in 'containers.daily_counts' where the key starts with YYYYMM\n"
            "   - Example: For February 2025, sum all values where key starts with '202502'\n"
            "   - For date range queries: Sum values for all dates in that range\n"
            "\n"
            "4. RESPONSE FORMAT:\n"
            "   - Always provide the exact number found\n"
            "   - Answer in Hebrew\n"
            "   - Format: 'בחודש [חודש] [שנה] נפרקו [מספר] מכולות'\n"
            "   - If data not found, explain what you searched for (e.g., 'חיפשתי מכולות בפברואר 2025 אך לא מצאתי נתונים')"
        )
        return "\n\n".join(parts)

