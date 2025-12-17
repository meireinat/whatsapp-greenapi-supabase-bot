"""
Utilities for crafting human-friendly responses sent back to WhatsApp users.
"""

from __future__ import annotations

import datetime as dt
from typing import Sequence

from app.services.container_status import PortStatusResult


def build_daily_containers_response(count: int, target_date: dt.date) -> str:
    human_date = target_date.strftime("%d/%m/%Y")
    return (
        f"{human_date} | מספר המכולות שטופלו הוא {count}.\n"
        "למידע נוסף, שאל שאלה אחרת או בקש סיכום נוסף."
    )


def build_containers_range_response(
    count: int, start_date: dt.date, end_date: dt.date
) -> str:
    return (
        f"בין {start_date.strftime('%d/%m/%Y')} ל-{end_date.strftime('%d/%m/%Y')} "
        f"נפרקו {count} מכולות."
    )


def build_vehicles_range_response(
    count: int, start_date: dt.date, end_date: dt.date
) -> str:
    return (
        f"בין {start_date.strftime('%d/%m/%Y')} ל-{end_date.strftime('%d/%m/%Y')} "
        f"טופלו {count} רכבים."
    )


def build_monthly_containers_response(count: int, month: int, year: int) -> str:
    """Build response for monthly container count query."""
    month_names_he = {
        1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל",
        5: "מאי", 6: "יוני", 7: "יולי", 8: "אוגוסט",
        9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
    }
    month_name = month_names_he.get(month, f"חודש {month}")
    return (
        f"בחודש {month_name} {year} נפרקו {count} מכולות."
    )


def build_comparison_containers_response(
    count1: int, month1: int, year1: int,
    count2: int, month2: int, year2: int,
    difference: int,
) -> str:
    """Format response for monthly container count comparison."""
    month_names_he = {
        1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל",
        5: "מאי", 6: "יוני", 7: "יולי", 8: "אוגוסט",
        9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
    }
    month1_name = month_names_he.get(month1, f"חודש {month1}")
    month2_name = month_names_he.get(month2, f"חודש {month2}")
    
    if difference > 0:
        diff_text = f"עלייה של {difference} מכולות"
        if count1 > 0:
            percent = (difference / count1) * 100
            diff_text += f" ({percent:+.1f}%)"
    elif difference < 0:
        diff_text = f"ירידה של {abs(difference)} מכולות"
        if count1 > 0:
            percent = (difference / count1) * 100
            diff_text += f" ({percent:+.1f}%)"
    else:
        diff_text = "אותו מספר מכולות"
    
    return (
        f"בחודש {month1_name} {year1} נפרקו {count1} מכולות.\n"
        f"בחודש {month2_name} {year2} נפרקו {count2} מכולות.\n"
        f"ההבדל: {diff_text}."
    )


def build_fallback_response() -> str:
    return (
        "מצטער, לא הצלחתי להבין את הבקשה או לא מצאתי מידע רלוונטי. "
        "נסה לנסח מחדש את השאלה או לשאול שאלה אחרת.\n\n"
        "דוגמאות לשאלות שאני יכול לענות עליהן:\n"
        "• כמה מכולות נפרקו בחודש מסוים (למשל בחודש ינואר 2024)?\n"
        "• סטטוס מכולה עבור מספר מכולה מסוים\n"
        "• השוואה בין כמות מכולות בשני חודשים שונים"
    )


def build_container_status_response(
    container_id: str, results: Sequence[PortStatusResult]
) -> str:
    lines: list[str] = [f"סטטוס מכולה {container_id.upper()}"]

    for result in results:
        status_emoji = "✅" if result.success else "⚠️"
        lines.append(f"{status_emoji} {result.port_name} – {result.summary}")
        if result.error and not result.success:
            lines.append(f"• סיבה: {result.error}")
        if result.details:
            for label, value in result.details:
                lines.append(f"• {label}: {value}")

    lines.append("הנתונים מתקבלים ישירות מאתרי הנמלים ועשויים להתעדכן מעת לעת.")
    return "\n".join(lines).strip()

