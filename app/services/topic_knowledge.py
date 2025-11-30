"""
Knowledge base that reads files from fwai/downloads directory.
The topic/subject is extracted from the filename.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "fwai" / "downloads"
)


@dataclass(frozen=True, slots=True)
class TopicSection:
    """
    Represents a single chunk extracted from a topic file.
    """

    section_id: str
    topic: str
    source_file: str
    text: str
    text_lower: str


class TopicKnowledgeBase:
    """
    Provides paragraph-level retrieval over topic files from fwai/downloads.
    The topic is extracted from the filename.
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        self._data_path = Path(data_path or DEFAULT_DATA_PATH)
        self._sections: list[TopicSection] = self._load_sections(self._data_path)

    @staticmethod
    def _extract_topic_from_filename(filename: str) -> str:
        """
        Extract topic from filename by removing extension and cleaning up.
        Examples:
        - "מכולות_סטטוס.txt" -> "מכולות סטטוס"
        - "תקנות_נמל.pdf" -> "תקנות נמל"
        - "topic-name.txt" -> "topic name"
        """
        # Remove extension
        name = Path(filename).stem
        
        # Replace common separators with spaces
        name = re.sub(r"[_\-\s]+", " ", name)
        
        # Clean up multiple spaces
        name = re.sub(r"\s+", " ", name).strip()
        
        return name if name else filename

    @staticmethod
    def _split_into_chunks(text: str, chunk_size: int = 1000) -> list[str]:
        """
        Split text into chunks of approximately chunk_size characters.
        Tries to break at paragraph boundaries (double newlines) or sentence boundaries.
        """
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        
        chunks: list[str] = []
        remaining = text
        
        while len(remaining) > chunk_size:
            # Try to break at paragraph boundary first
            para_break = remaining.rfind("\n\n", 0, chunk_size)
            if para_break > chunk_size // 2:
                chunks.append(remaining[:para_break].strip())
                remaining = remaining[para_break + 2:].lstrip()
                continue
            
            # Try to break at sentence boundary
            sentence_break = max(
                remaining.rfind(". ", 0, chunk_size),
                remaining.rfind(".\n", 0, chunk_size),
                remaining.rfind("! ", 0, chunk_size),
                remaining.rfind("? ", 0, chunk_size),
            )
            if sentence_break > chunk_size // 2:
                chunks.append(remaining[:sentence_break + 1].strip())
                remaining = remaining[sentence_break + 1:].lstrip()
                continue
            
            # Fallback: break at word boundary
            word_break = remaining.rfind(" ", 0, chunk_size)
            if word_break > chunk_size // 2:
                chunks.append(remaining[:word_break].strip())
                remaining = remaining[word_break:].lstrip()
            else:
                # Force break if no good boundary found
                chunks.append(remaining[:chunk_size].strip())
                remaining = remaining[chunk_size:].lstrip()
        
        if remaining.strip():
            chunks.append(remaining.strip())
        
        return chunks

    @classmethod
    def _load_sections(cls, path: Path) -> list[TopicSection]:
        """
        Load all files from the directory and create sections.
        Each file's topic is extracted from its filename.
        """
        if not path.exists():
            logger.warning(
                "Topic knowledge directory not found at %s. Topic-based answers will not include file context.",
                path,
            )
            return []

        sections: list[TopicSection] = []
        supported_extensions = {".txt", ".md", ".json", ".csv"}
        
        try:
            # Get all files in the directory (exclude README files)
            files = [
                f for f in path.iterdir()
                if f.is_file()
                and f.suffix.lower() in supported_extensions
                and not f.name.upper().startswith("README")
            ]
            
            if not files:
                logger.warning("No supported files found in %s (looking for .txt, .md, .json, .csv)", path)
                return []
            
            logger.info("Found %d files in %s", len(files), path)
            
            for file_path in files:
                try:
                    topic = cls._extract_topic_from_filename(file_path.name)
                    logger.debug("Processing file: %s (topic: %s)", file_path.name, topic)
                    
                    # Read file content
                    encoding = "utf-8"
                    try:
                        content = file_path.read_text(encoding=encoding)
                    except UnicodeDecodeError:
                        # Try other common encodings
                        for enc in ["cp1255", "iso-8859-8", "latin1"]:
                            try:
                                content = file_path.read_text(encoding=enc)
                                encoding = enc
                                break
                            except (UnicodeDecodeError, LookupError):
                                continue
                        else:
                            logger.warning("Could not decode file %s with any encoding, skipping", file_path.name)
                            continue
                    
                    if not content.strip():
                        logger.debug("File %s is empty, skipping", file_path.name)
                        continue
                    
                    # Split into chunks
                    chunks = cls._split_into_chunks(content)
                    logger.debug("Split file %s into %d chunks", file_path.name, len(chunks))
                    
                    # Create sections from chunks
                    for idx, chunk_text in enumerate(chunks):
                        section_id = f"{file_path.stem}-{idx + 1}"
                        sections.append(
                            TopicSection(
                                section_id=section_id,
                                topic=topic,
                                source_file=file_path.name,
                                text=chunk_text,
                                text_lower=chunk_text.lower(),
                            )
                        )
                    
                except Exception as exc:
                    logger.error(
                        "Failed to process file %s: %s",
                        file_path.name,
                        exc,
                        exc_info=True,
                    )
                    continue
            
            logger.info(
                "Loaded %d topic sections from %d files in %s",
                len(sections),
                len(files),
                path,
            )
            
        except Exception as exc:
            logger.error("Failed to load topic knowledge from %s: %s", path, exc, exc_info=True)
            return []
        
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
                "topic": section.topic,
                "source_file": section.source_file,
                "excerpt": section.text,
            }
            for section in matches
        ]

    def _search(self, query: str, *, limit: int) -> Sequence[TopicSection]:
        if not self._sections:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return self._sections[:limit]

        ranked: list[tuple[float, TopicSection]] = []
        for section in self._sections:
            score = self._score_section(section, tokens)
            if score > 0:
                ranked.append((score, section))

        if not ranked:
            return self._sections[:limit]

        ranked.sort(key=lambda pair: pair[0], reverse=True)

        seen: set[str] = set()
        results: list[TopicSection] = []
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
    def _score_section(section: TopicSection, tokens: Iterable[str]) -> float:
        score = 0.0
        text = section.text_lower
        length = max(len(text), 1)
        
        # Boost score if topic name matches query tokens
        topic_lower = section.topic.lower()
        topic_tokens = TopicKnowledgeBase._tokenize(topic_lower)
        topic_match_boost = 0.0
        for token in tokens:
            if token in topic_tokens:
                topic_match_boost += 2.0  # Boost for topic matches
        
        for token in tokens:
            occurrences = text.count(token)
            if occurrences:
                score += occurrences * (len(token) / length)
        
        score += topic_match_boost
        return score

