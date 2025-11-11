"""
Gemini client wrapper for advanced analytical responses based on Supabase data.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Mapping

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
    ) -> str:
        """
        Generate a response using Gemini with the provided metrics context.
        """

        def _call() -> str:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
                or (
                    "You are a data analyst for a port operations team. "
                    "Answer in Hebrew, using only the data provided in the JSON context. "
                    "If the context lacks information required to answer accurately, "
                    "state clearly what is missing instead of guessing."
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
                temperature=0.3,
            )
            prompt = self._build_prompt(question=question, metrics=metrics)
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
            return (response.text or "").strip()

        return await asyncio.to_thread(_call)

    @staticmethod
    def _build_prompt(*, question: str, metrics: Mapping[str, Any]) -> str:
        context = json.dumps(metrics, ensure_ascii=False, indent=2)
        return (
            "Contextual data (JSON):\n"
            f"{context}\n\n"
            "Using only the context above, answer the following question:\n"
            f"{question}"
        )

