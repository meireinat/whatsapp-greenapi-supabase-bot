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
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\w+)\s+(?P<year>\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bכמה\b.*\bמכולות\b.*?(?:ב|בחודש)\s*(?P<month_name>\w+)",
            re.IGNORECASE,
        ),
    )

    LLM_ANALYSIS_PATTERNS = (
        re.compile(r"\b(?:ניתוח|נתח|גמיני|Gemini|AI)\b", re.IGNORECASE),
    )

    def match(self, text: str) -> IntentResult | None:
        stripped = text.strip()
        if not stripped:
            return None

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

        for pattern in self.MONTHLY_CONTAINER_PATTERNS:
            match = pattern.search(stripped)
            if match:
                month_params = self._parse_month(match.groupdict())
                if month_params:
                    return IntentResult(
                        name="containers_count_monthly",
                        parameters=month_params,
                    )

        for pattern in self.LLM_ANALYSIS_PATTERNS:
            match = pattern.search(stripped)
            if match:
                dates = self._extract_any_range(stripped)
                params: dict[str, object] = {"question": stripped}
                if dates:
                    params.update(dates)
                return IntentResult(name="llm_analysis", parameters=params)

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
            "ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "מארס": 3,
            "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
            "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
        }
        month_names_en = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        
        month_name = groups.get("month_name", "").strip().lower()
        if not month_name:
            return None
        
        # Try Hebrew first, then English
        month_num = month_names_he.get(month_name) or month_names_en.get(month_name)
        if not month_num:
            return None
        
        # Parse year (default to current year if not provided)
        year_text = groups.get("year", "")
        if year_text:
            year = int(year_text)
            if year < 100:
                year += 2000 if year < 80 else 1900
        else:
            year = dt.date.today().year
        
        return {"month": month_num, "year": year}

