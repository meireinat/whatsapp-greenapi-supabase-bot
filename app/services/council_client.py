"""
LLM Council client wrapper for multi-model responses with ranking.
Integrates with the LLM Council system to get responses from multiple models,
rank them, and synthesize a final answer.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Mapping, Sequence

import httpx


class CouncilService:
    """
    Provides an interface to LLM Council for multi-model responses with ranking.
    """

    def __init__(
        self,
        api_key: str,
        council_models: list[str] | None = None,
        chairman_model: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self._api_key = api_key
        self._api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Default models if not provided
        self._council_models = council_models or [
            "openai/gpt-4o",
            "google/gemini-2.0-flash-exp",
            "anthropic/claude-3.5-sonnet",
        ]
        self._chairman_model = chairman_model or "google/gemini-2.0-flash-exp"

    async def answer_question(
        self,
        *,
        question: str,
        metrics: Mapping[str, Any],
        system_instruction: str | None = None,
        knowledge_sections: Sequence[Mapping[str, str]] | None = None,
        conversation_history: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        """
        Generate a response using LLM Council with the provided metrics context.
        Returns the final synthesized answer from the Chairman.
        """
        # Build the prompt with context
        prompt = self._build_prompt(
            question=question,
            metrics=metrics,
            knowledge_sections=knowledge_sections,
            conversation_history=conversation_history,
        )

        # Build system instruction
        system_instruction_text = system_instruction or self._get_default_system_instruction()

        # Stage 1: Get responses from all council models
        stage1_results = await self._stage1_collect_responses(
            prompt, system_instruction_text
        )

        if not stage1_results:
            return "מצטער, לא הצלחתי לקבל תשובות מהמודלים. אנא נסה שוב."

        # Stage 2: Get rankings from all models
        stage2_results, label_to_model = await self._stage2_collect_rankings(
            question, prompt, stage1_results, system_instruction_text
        )

        # Stage 3: Synthesize final answer
        final_response = await self._stage3_synthesize_final(
            question, prompt, stage1_results, stage2_results, system_instruction_text
        )

        return final_response

    async def _stage1_collect_responses(
        self, prompt: str, system_instruction: str
    ) -> list[dict[str, Any]]:
        """Stage 1: Collect individual responses from all council models."""
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        # Query all models in parallel
        tasks = [
            self._query_model(model, messages) for model in self._council_models
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        stage1_results = []
        for model, response in zip(self._council_models, responses):
            if isinstance(response, Exception):
                continue
            if response and response.get("content"):
                stage1_results.append(
                    {"model": model, "response": response.get("content", "")}
                )

        return stage1_results

    async def _stage2_collect_rankings(
        self,
        question: str,
        original_prompt: str,
        stage1_results: list[dict[str, Any]],
        system_instruction: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Stage 2: Each model ranks the anonymized responses."""
        # Create anonymized labels
        labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

        # Create mapping from label to model name
        label_to_model = {
            f"Response {label}": result["model"]
            for label, result in zip(labels, stage1_results)
        }

        # Build the ranking prompt
        responses_text = "\n\n".join(
            [
                f"Response {label}:\n{result['response']}"
                for label, result in zip(labels, stage1_results)
            ]
        )

        ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {question}

Original Context:
{original_prompt}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": ranking_prompt},
        ]

        # Get rankings from all council models in parallel
        tasks = [
            self._query_model(model, messages) for model in self._council_models
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        stage2_results = []
        for model, response in zip(self._council_models, responses):
            if isinstance(response, Exception):
                continue
            if response and response.get("content"):
                full_text = response.get("content", "")
                parsed = self._parse_ranking_from_text(full_text)
                stage2_results.append(
                    {
                        "model": model,
                        "ranking": full_text,
                        "parsed_ranking": parsed,
                    }
                )

        return stage2_results, label_to_model

    async def _stage3_synthesize_final(
        self,
        question: str,
        original_prompt: str,
        stage1_results: list[dict[str, Any]],
        stage2_results: list[dict[str, Any]],
        system_instruction: str,
    ) -> str:
        """Stage 3: Chairman synthesizes final response."""
        # Build comprehensive context for chairman
        stage1_text = "\n\n".join(
            [
                f"Model: {result['model']}\nResponse: {result['response']}"
                for result in stage1_results
            ]
        )

        stage2_text = "\n\n".join(
            [
                f"Model: {result['model']}\nRanking: {result['ranking']}"
                for result in stage2_results
            ]
        )

        chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {question}

Original Context:
{original_prompt}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer in Hebrew that represents the council's collective wisdom:"""

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": chairman_prompt},
        ]

        # Query the chairman model
        response = await self._query_model(self._chairman_model, messages)

        if not response or not response.get("content"):
            # Fallback to best ranked response from stage 1
            if stage1_results:
                return stage1_results[0]["response"]
            return "מצטער, לא הצלחתי ליצור תשובה סופית."

        return response.get("content", "").strip()

    async def _query_model(
        self, model: str, messages: list[dict[str, str]], timeout: float = 120.0
    ) -> dict[str, Any] | None:
        """Query a single model via OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._api_url, headers=headers, json=payload
                )
                response.raise_for_status()

                data = response.json()
                message = data["choices"][0]["message"]

                return {
                    "content": message.get("content"),
                    "reasoning_details": message.get("reasoning_details"),
                }
        except Exception as e:
            # Log error but don't crash
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error querying model {model}: {e}")
            return None

    @staticmethod
    def _parse_ranking_from_text(ranking_text: str) -> list[str]:
        """Parse the FINAL RANKING section from the model's response."""
        import re

        # Look for "FINAL RANKING:" section
        if "FINAL RANKING:" in ranking_text:
            # Extract everything after "FINAL RANKING:"
            parts = ranking_text.split("FINAL RANKING:")
            if len(parts) >= 2:
                ranking_section = parts[1]
                # Try to extract numbered list format (e.g., "1. Response A")
                numbered_matches = re.findall(
                    r"\d+\.\s*Response [A-Z]", ranking_section
                )
                if numbered_matches:
                    # Extract just the "Response X" part
                    return [
                        re.search(r"Response [A-Z]", m).group() for m in numbered_matches
                    ]

                # Fallback: Extract all "Response X" patterns in order
                matches = re.findall(r"Response [A-Z]", ranking_section)
                return matches

        # Fallback: try to find any "Response X" patterns in order
        matches = re.findall(r"Response [A-Z]", ranking_text)
        return matches

    @staticmethod
    def _build_prompt(
        *,
        question: str,
        metrics: Mapping[str, Any],
        knowledge_sections: Sequence[Mapping[str, str]] | None = None,
        conversation_history: Sequence[Mapping[str, Any]] | None = None,
    ) -> str:
        """Build the prompt with context and metrics."""
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
        else:
            parts.append("Note: No specific knowledge base excerpts were found for this question.")
            parts.append("You should use your general knowledge about port operations, maritime regulations, and operational procedures to answer.")
        
        parts.append("Question:")
        parts.append(question)
        parts.append("\n")
        parts.append("Instructions:")
        parts.append("- Answer the question based on the context provided above (metrics data)")
        parts.append("- If the question is about operational procedures, regulations, port operations, or job requirements:")
        parts.append("  * First check if knowledge base excerpts are available and use them")
        parts.append("  * If no excerpts are available, use your general knowledge about port operations, maritime industry, and Israeli port regulations")
        parts.append("  * Provide a helpful, accurate answer based on standard industry practices")
        parts.append("- For questions about data (containers, vehicles, dates): use only the metrics data provided")
        parts.append("- Always provide a clear, helpful answer in Hebrew")
        parts.append("- If you're using general knowledge (not from the provided data), you can mention it, but still provide the answer")
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

    @staticmethod
    def _get_default_system_instruction() -> str:
        """Get the default system instruction."""
        return (
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
            "For operational questions (e.g., procedures, regulations, port operations, job requirements):\n"
            "- Use information from knowledge base excerpts if provided\n"
            "- If no relevant excerpts are provided, you MUST use your general knowledge about:\n"
            "  * Port operations and maritime industry standards\n"
            "  * Israeli port regulations and procedures\n"
            "  * Common operational requirements and best practices\n"
            "- Be specific and practical in your answers\n"
            "- DO NOT say 'no information available' - instead provide an answer based on general knowledge\n"
            "- You can mention that the answer is based on general knowledge, but still provide the information\n"
            "\n"
            "If the context lacks information required to answer accurately, "
            "state clearly what is missing instead of guessing."
        )

