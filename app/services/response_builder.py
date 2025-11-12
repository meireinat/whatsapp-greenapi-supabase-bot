"""
Utilities for crafting human-friendly responses sent back to WhatsApp users.
"""

from __future__ import annotations

import datetime as dt


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


def build_fallback_response() -> str:
    return (
        "מצטער, לא הצלחתי להבין את הבקשה. "
        "נסה לנסח מחדש או לשאול שאלה אחרת."
    )

