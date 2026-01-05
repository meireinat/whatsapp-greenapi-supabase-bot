"""
Simple rule-based intent engine for the initial bot version.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from collections.abc import Mapping

DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})[./-](?P<month>\d{1,2})[./-](?P<year>\d{2,4})"
)
DATE_PATTERN_INLINE = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"


@dataclasses.dataclass(slots=True)
class IntentResult:
    name: str
    parameters: Mapping[str, object]


class IntentEngine:
    """
    Minimal intent detection engine based on keyword heuristics.
    """

    DAILY_CONTAINER_PATTERNS = (
        re.compile(r"\bכמה\b.*\bמכולות\b.*\bהיום\b", re.IGNORECASE),
        re.compile(r"\bcontainers\b.*\btoday\b", re.IGNORECASE),
    )

    RANGE_CONTAINER_PATTERNS = (
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:בין|מתאריך)\s+(?P<from>{date}).*?(?:עד|ל)\s*(?P<to>{date})".format(
                date=DATE_PATTERN_INLINE
            ),
            re.IGNORECASE,
        ),
    )

    RANGE_VEHICLES_PATTERNS = (
        re.compile(
            r"\bכמה\b.*\b(?:רכבים|vehicles)\b.*?(?:בין|מתאריך)\s+(?P<from>{date}).*?(?:עד|ל)\s*(?P<to>{date})".format(
                date=DATE_PATTERN_INLINE
            ),
            re.IGNORECASE,
        ),
    )

    MONTHLY_CONTAINER_PATTERNS = (
        # Support with verbs FIRST (more specific): "כמה מכולות נפרקו בפברואר 25"
        # This handles "ב" directly attached to month name: "בפברואר" as one word
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:נפרקו|עשו|עשה|טופלו|היו)\s+ב(?P<month_name>\S+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:נפרקו|עשו|עשה|טופלו|היו)\s+ב(?P<month_name>\S+)",
            re.IGNORECASE,
        ),
        # Support with verbs and space: "כמה מכולות נפרקו ב פברואר 25"
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:נפרקו|עשו|עשה|טופלו|היו)\s+(?:ב|בחודש|ב-|בחודש-)\s*(?P<month_name>\S+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:נפרקו|עשו|עשה|טופלו|היו)\s+(?:ב|בחודש|ב-|בחודש-)\s*(?P<month_name>\S+)",
            re.IGNORECASE,
        ),
        # Hebrew: "כמה מכולות בינואר 2024" or "כמה מכולות בחודש ינואר 2024"
        # Use \S+ to match any non-whitespace characters (including Hebrew)
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\S+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\S+)",
            re.IGNORECASE,
        ),
        # Also support without "חודש": "כמה מכולות בינואר 2024"
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?ב(?P<month_name>\S+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?ב(?P<month_name>\S+)",
            re.IGNORECASE,
        ),
        # English month names
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\w+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\w+)",
            re.IGNORECASE,
        ),
    )

    # Comparison patterns: "כמה מכולות בינואר 2024 לעומת ינואר 2025"
    COMPARISON_MONTHLY_PATTERNS = (
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month1_name>\S+)\s+(?P<year1>\d{2,4})\s+(?:לעומת|מול|vs|versus)\s+(?:ב|בחודש)?\s*(?P<month2_name>\S+)\s+(?P<year2>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month1_name>\S+)\s+(?P<year1>\d{2,4})\s+(?:לעומת|מול|vs|versus)\s+(?:ב|בחודש)?\s*(?P<month2_name>\S+)(?:\s+(?P<year2>\d{2,4}))?",
            re.IGNORECASE,
        ),
    )

    LLM_ANALYSIS_PATTERNS = (
        re.compile(r"\b(?:ניתוח|נתח|גמיני|Gemini|AI)\b", re.IGNORECASE),
    )

    CONTAINER_STATUS_PATTERNS = (
        re.compile(r"\b(?:סטטוס|מצב)\b.*\bמכול", re.IGNORECASE),
        re.compile(r"\bcontainer\s+status\b", re.IGNORECASE),
        re.compile(r"\bMISMHOLA\b", re.IGNORECASE),
    )

    # Generic container-related questions (fallback to Gemini with metrics)
    CONTAINER_GENERIC_PATTERNS = (
        re.compile(r"\bמכול", re.IGNORECASE),          # כל מופע של "מכול" / "מכולות" / "מכולה"
        re.compile(r"\bcontainer[s]?\b", re.IGNORECASE),
    )

    CONTAINER_ID_PATTERN = re.compile(r"\b([A-Z]{4}\d{7}|\d{9,12})\b", re.IGNORECASE)

    MANAGER_QUESTION_PATTERNS = (
        re.compile(r"אני\s+מנהל", re.IGNORECASE),
        re.compile(r"I\s+am\s+a\s+manager", re.IGNORECASE),
        re.compile(r"I'm\s+a\s+manager", re.IGNORECASE),
    )

    # Patterns for procedure/policy questions - should query NotebookLM
    PROCEDURE_QUESTION_PATTERNS = (
        re.compile(r"\b(?:נהל|נהלים|תהליך|תהליכים|מדיניות|פרוצדורה|פרוצדורות)\b", re.IGNORECASE),
        re.compile(r"\b(?:procedure|procedures|policy|policies|process|processes)\b", re.IGNORECASE),
        re.compile(r"\b(?:תור|תורים|עדיפות|עדיפויות)\b.*\b(?:נמל|אוניה|אוניות|מכולה|מכולות)", re.IGNORECASE),
        re.compile(r"\b(?:עקוף|עוקף|עוקפות|עוקפים)\b.*\b(?:תור|תורים)", re.IGNORECASE),
        re.compile(r"\b(?:queue|queuing|priority|priorities)\b", re.IGNORECASE),
        # Pattern for questions about nuclear ships and queue/priority
        re.compile(r"\b(?:גרעינים|גרעין)\b", re.IGNORECASE),
        # Pattern for questions about bypassing queue
        re.compile(r"\b(?:עקוף|עוקף|עוקפות|עוקפים)\b", re.IGNORECASE),
        # Pattern for questions about ships and queue
        re.compile(r"\b(?:אוניה|אוניות|אוניית)\b.*\b(?:תור|תורים|עקוף)", re.IGNORECASE),
    )

    def match(self, text: str) -> IntentResult | None:
        import logging
        logger = logging.getLogger(__name__)
        
        stripped = text.strip()
        if not stripped:
            return None

        logger.info("Matching intent for text: %s (length: %d)", stripped, len(stripped))

        # Check for procedure/policy questions first (should query NotebookLM)
        for pattern in self.PROCEDURE_QUESTION_PATTERNS:
            if pattern.search(stripped):
                return IntentResult(
                    name="procedure_question",
                    parameters={"question": stripped},
                )

        # Check for manager questions (high priority)
        for pattern in self.MANAGER_QUESTION_PATTERNS:
            if pattern.search(stripped):
                return IntentResult(
                    name="manager_question",
                    parameters={"question": stripped},
                )

        for pattern in self.DAILY_CONTAINER_PATTERNS:
            if pattern.search(stripped):
                return IntentResult(
                    name="daily_containers_count",
                    parameters={"target_date": dt.date.today()},
                )

        for pattern in self.RANGE_CONTAINER_PATTERNS:
            match = pattern.search(stripped)
            if match:
                dates = self._parse_range(match.groupdict())
                if dates:
                    return IntentResult(
                        name="containers_count_between",
                        parameters=dates,
                    )

        for pattern in self.RANGE_VEHICLES_PATTERNS:
            match = pattern.search(stripped)
            if match:
                dates = self._parse_range(match.groupdict())
                if dates:
                    return IntentResult(
                        name="vehicles_count_between",
                        parameters=dates,
                    )

        # Check for comparison patterns first (more specific)
        for i, pattern in enumerate(self.COMPARISON_MONTHLY_PATTERNS):
            match = pattern.search(stripped)
            if match:
                logger.info("COMPARISON_MONTHLY_PATTERNS[%d] matched: %s", i, match.groupdict())
                comparison_params = self._parse_comparison(match.groupdict())
                if comparison_params:
                    logger.info("Parsed comparison params: %s", comparison_params)
                    return IntentResult(
                        name="containers_count_comparison",
                        parameters=comparison_params,
                    )
                else:
                    logger.warning("Failed to parse comparison from: %s", match.groupdict())

        for i, pattern in enumerate(self.MONTHLY_CONTAINER_PATTERNS):
            match = pattern.search(stripped)
            if match:
                logger.info("MONTHLY_CONTAINER_PATTERNS[%d] matched: %s", i, match.groupdict())
                month_params = self._parse_month(match.groupdict())
                if month_params:
                    logger.info("Parsed month params: %s", month_params)
                    return IntentResult(
                        name="containers_count_monthly",
                        parameters=month_params,
                    )
                else:
                    logger.warning("Failed to parse month from: %s", match.groupdict())

        for pattern in self.LLM_ANALYSIS_PATTERNS:
            match = pattern.search(stripped)
            if match:
                dates = self._extract_any_range(stripped)
                params: dict[str, object] = {"question": stripped}
                if dates:
                    params.update(dates)
                return IntentResult(name="llm_analysis", parameters=params)

        # Check for container status lookup BEFORE generic container patterns
        # (container status is more specific than generic container questions)
        for pattern in self.CONTAINER_STATUS_PATTERNS:
            if pattern.search(stripped):
                container_id = self._extract_container_id(stripped)
                if container_id:
                    return IntentResult(
                        name="container_status_lookup",
                        parameters={"container_id": container_id},
                    )

        # If a container id was provided without explicit keywords, still try to help.
        container_id = self._extract_container_id(stripped)
        if container_id:
            return IntentResult(
                name="container_status_lookup",
                parameters={"container_id": container_id},
            )

        # Any other container-related question that didn't match a specific intent
        # will go through LLM analysis with metrics (Gemini "מדייק" את השאלה)
        # This should come AFTER container_status_lookup to avoid false matches
        for pattern in self.CONTAINER_GENERIC_PATTERNS:
            if pattern.search(stripped):
                return IntentResult(
                    name="llm_analysis",
                    parameters={"question": stripped},
                )

        logger.info("No intent matched for text: %s", stripped)
        return None

    def _parse_range(self, groups: Mapping[str, str]) -> dict[str, dt.date] | None:
        try:
            start_text = groups["from"]
            end_text = groups["to"]
        except KeyError:
            return None

        start_date = self._parse_date(start_text)
        end_date = self._parse_date(end_text)
        if not start_date or not end_date:
            return None

        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return {"start_date": start_date, "end_date": end_date}

    @staticmethod
    def _parse_date(text: str) -> dt.date | None:
        match = DATE_PATTERN.search(text)
        if not match:
            return None
        day = int(match.group("day"))
        month = int(match.group("month"))
        year = int(match.group("year"))
        if year < 100:
            year += 2000 if year < 80 else 1900
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None

    def _extract_any_range(self, text: str) -> dict[str, dt.date] | None:
        matches = [self._parse_date(m.group(0)) for m in DATE_PATTERN.finditer(text)]
        valid = [d for d in matches if d]
        if len(valid) < 2:
            return None
        first, second = valid[0], valid[1]
        if first > second:
            first, second = second, first
        return {"start_date": first, "end_date": second}

    @staticmethod
    def _parse_month(groups: Mapping[str, str]) -> dict[str, int] | None:
        """Parse month name and year from Hebrew or English."""
        month_names_he = {
            "ינואר": 1, 
            "פברואר": 2, "פבאור": 2, "פבואר": 2, "פברואר": 2,  # Common variations
            "מרץ": 3, "מרס": 3, "מארס": 3, "מרץ": 3,
            "אפריל": 4, 
            "מאי": 5, 
            "יוני": 6, 
            "יולי": 7, 
            "אוגוסט": 8,
            "ספטמבר": 9, 
            "אוקטובר": 10, 
            "נובמבר": 11, 
            "דצמבר": 12,
        }
        month_names_en = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        
        month_name = IntentEngine._clean_token(groups.get("month_name", ""))
        if not month_name:
            return None
        
        # Try Hebrew first (case-sensitive for Hebrew)
        month_num = month_names_he.get(month_name)
        # Then try English (case-insensitive)
        if not month_num:
            month_num = month_names_en.get(month_name.lower())
        
        if not month_num:
            return None
        
        # Parse year (default to current year if not provided)
        year_text = IntentEngine._clean_token(groups.get("year", ""))
        if year_text:
            year = int(year_text)
            if year < 100:
                year += 2000 if year < 80 else 1900
        else:
            year = dt.date.today().year
        
        return {"month": month_num, "year": year}

    @staticmethod
    def _parse_comparison(groups: Mapping[str, str]) -> dict[str, int] | None:
        """Parse two months for comparison: month1/year1 vs month2/year2."""
        month1_params = IntentEngine._parse_month({
            "month_name": IntentEngine._clean_token(groups.get("month1_name", "")),
            "year": IntentEngine._clean_token(groups.get("year1", "")),
        })
        if not month1_params:
            return None
        
        # For second month, use year2 if provided, otherwise use year1 (same year comparison)
        year2_text = IntentEngine._clean_token(groups.get("year2", ""))
        if not year2_text:
            # If no year2, assume same year as year1
            year2_text = str(month1_params["year"])
        
        month2_params = IntentEngine._parse_month({
            "month_name": IntentEngine._clean_token(groups.get("month2_name", "")),
            "year": year2_text,
        })
        if not month2_params:
            return None
        
        return {
            "month1": month1_params["month"],
            "year1": month1_params["year"],
            "month2": month2_params["month"],
            "year2": month2_params["year"],
        }

    def _extract_container_id(self, text: str) -> str | None:
        """
        Try to extract a container identifier (either ISO format or MISMHOLA numeric).
        """
        match = self.CONTAINER_ID_PATTERN.search(text)
        if match:
            candidate = match.group(1).upper()
            return candidate
        mis_idx = text.lower().find("mismhola=")
        if mis_idx != -1:
            candidate = text[mis_idx + len("mismhola=") : mis_idx + len("mismhola=") + 12]
            candidate = re.split(r"\s|&", candidate)[0]
            return candidate.upper()
        return None

    @staticmethod
    def _clean_token(token: str | None) -> str:
        if not token:
            return ""
        return token.strip(" \t\n\r.,?!:;\"'()[]{}")

