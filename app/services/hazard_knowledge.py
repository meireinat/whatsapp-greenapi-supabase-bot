"""
Lightweight knowledge base built from hazardous cargo PDF documents.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "hazard" / "hazard_documents.json"
)


@dataclass(frozen=True, slots=True)
class HazardSection:
    """
    Represents a single chunk extracted from a hazardous cargo document.
    """

    section_id: str
    document_id: str
    document_title: str
    source_file: str
    text: str
    text_lower: str


class HazardKnowledgeBase:
    """
    Provides paragraph-level retrieval over hazardous cargo PDF excerpts.
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        self._data_path = Path(data_path or DEFAULT_DATA_PATH)
        self._sections: list[HazardSection] = self._load_sections(self._data_path)

    @staticmethod
    def _load_sections(path: Path) -> list[HazardSection]:
        if not path.exists():
            logger.warning(
                "Hazard knowledge file not found at %s. Gemini answers will not include document context.",
                path,
            )
            return []

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load hazard knowledge JSON: %s", exc, exc_info=True)
            return []

        sections: list[HazardSection] = []
        for document in data.get("documents", []):
            doc_id = document.get("id") or "unknown"
            title = document.get("title") or doc_id
            source_file = document.get("source_file", "hazard.pdf")
            for chunk in document.get("chunks", []):
                text = (chunk.get("text") or "").strip()
                if not text:
                    continue
                section_id = chunk.get("id") or f"{doc_id}-{len(sections)+1}"
                sections.append(
                    HazardSection(
                        section_id=section_id,
                        document_id=doc_id,
                        document_title=title,
                        source_file=source_file,
                        text=text,
                        text_lower=text.lower(),
                    )
                )
        logger.info(
            "Loaded %d hazard document sections from %s",
            len(sections),
            path,
        )
        return sections

    def is_available(self) -> bool:
        return bool(self._sections)

    def build_sections(
        self,
        query: str,
        *,
        limit: int = 4,
    ) -> list[dict[str, str]]:
        """
        Return up to `limit` sections relevant to the supplied question.
        """
        matches = self._search(query, limit=limit)
        return [
            {
                "section_id": section.section_id,
                "document_id": section.document_id,
                "document_title": section.document_title,
                "source_file": section.source_file,
                "excerpt": section.text,
            }
            for section in matches
        ]

    def _search(self, query: str, *, limit: int) -> Sequence[HazardSection]:
        if not self._sections:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return self._sections[:limit]

        ranked: list[tuple[float, HazardSection]] = []
        for section in self._sections:
            score = self._score_section(section, tokens)
            if score > 0:
                ranked.append((score, section))

        if not ranked:
            return self._sections[:limit]

        ranked.sort(key=lambda pair: pair[0], reverse=True)

        seen: set[str] = set()
        results: list[HazardSection] = []
        for _, section in ranked:
            if section.section_id in seen:
                continue
            seen.add(section.section_id)
            results.append(section)
            if len(results) == limit:
                break
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        pattern = r"[A-Za-z\u0590-\u05FF0-9]+"
        return [token for token in re.findall(pattern, text.lower()) if token]

    @staticmethod
    def _score_section(section: HazardSection, tokens: Iterable[str]) -> float:
        score = 0.0
        text = section.text_lower
        length = max(len(text), 1)
        for token in tokens:
            occurrences = text.count(token)
            if occurrences:
                score += occurrences * (len(token) / length)
        return score


