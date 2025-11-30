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
    def _split_into_chunks(text: str, chunk_size: int = 2000) -> list[str]:
        """
        Split text into chunks by semantic units (sections, paragraphs) rather than just size.
        Tries to preserve meaning by breaking at natural boundaries.
        """
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        
        chunks: list[str] = []
        
        # First, try to split by clear section markers (better semantic meaning)
        section_markers = [
            r"\n\s*#{1,3}\s+",  # Markdown headers (# ## ###)
            r"\n\s*\d+[\.\)]\s+",  # Numbered sections (1. 2. 3.)
            r"\n\s*[א-ת]+[\.\)]\s+",  # Hebrew numbered sections
            r"\n\s*[•\-*]\s+",  # Bullet points (often indicate new topic)
        ]
        
        # Try each marker pattern
        for pattern in section_markers:
            matches = list(re.finditer(pattern, text))
            if len(matches) > 1:
                # Split by these markers, but respect chunk_size
                last_pos = 0
                current_chunk = ""
                
                for match in matches:
                    segment = text[last_pos:match.start()].strip()
                    if segment:
                        if len(current_chunk) + len(segment) + 2 <= chunk_size:
                            current_chunk += "\n\n" + segment if current_chunk else segment
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = segment
                    last_pos = match.start()
                
                # Add remaining
                remaining = text[last_pos:].strip()
                if remaining:
                    if len(current_chunk) + len(remaining) + 2 <= chunk_size:
                        current_chunk += "\n\n" + remaining if current_chunk else remaining
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        chunks.append(remaining)
                elif current_chunk:
                    chunks.append(current_chunk)
                
                if chunks:
                    return chunks
        
        # If no section markers, split by paragraphs (preserves semantic meaning)
        paragraphs = text.split("\n\n")
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk)
        
        # If still no chunks (very long paragraphs), fall back to sentence-based splitting
        if not chunks or any(len(c) > chunk_size * 1.5 for c in chunks):
            chunks = []
            remaining = text
            while len(remaining) > chunk_size:
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
                else:
                    # Fallback: break at word boundary
                    word_break = remaining.rfind(" ", 0, chunk_size)
                    if word_break > chunk_size // 2:
                        chunks.append(remaining[:word_break].strip())
                        remaining = remaining[word_break:].lstrip()
                    else:
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
        """
        Enhanced scoring algorithm that considers:
        1. Topic name matches (highest weight)
        2. Token frequency in text (weighted by token length)
        3. Token position (earlier in text = more relevant)
        """
        score = 0.0
        text = section.text_lower
        length = max(len(text), 1)
        token_list = list(tokens)  # Convert to list for multiple passes
        
        # 1. Topic name match (high boost - 3x weight)
        topic_lower = section.topic.lower()
        topic_tokens = TopicKnowledgeBase._tokenize(topic_lower)
        topic_match_count = sum(1 for token in token_list if token in topic_tokens)
        if topic_match_count > 0:
            score += topic_match_count * 3.0
        
        # 2. Text content matches (weighted by token length and position)
        for token in token_list:
            occurrences = text.count(token)
            if occurrences:
                # Weight by token length (longer tokens are more specific)
                token_weight = max(1.0, len(token) / 5.0)
                
                # Find first occurrence position (earlier = more relevant)
                first_pos = text.find(token)
                position_weight = 1.0 if first_pos == -1 else max(0.5, 1.0 - (first_pos / length))
                
                # Calculate score: frequency * token_weight * position_weight / length
                score += occurrences * token_weight * position_weight * (100.0 / length)
        
        # 3. Phrase matching bonus (if multiple consecutive tokens appear together)
        if len(token_list) >= 2:
            # Check for 2-word phrases
            for i in range(len(token_list) - 1):
                phrase = f"{token_list[i]} {token_list[i+1]}"
                if phrase in text:
                    score += 5.0  # Bonus for phrase matches
        
        return score

