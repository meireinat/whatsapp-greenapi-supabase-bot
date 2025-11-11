# טכנולוגיות וכלים

## 8.1 Backend – Python Bot Server

- שפה: **Python 3.11** (או גרסה נתמכת בארגון).
- Framework:
  - **FastAPI** (מומלץ ל-REST, ביצועים גבוהים, typing טוב).
  - לחלופין: Flask (למערכות פשוטות יותר).
- ספריות מומלצות:
  - `httpx` / `requests` – קריאות HTTP ל-Green API.
  - `supabase-py` – חיבור ל-Supabase.
  - `python-dotenv` – טעינת משתני סביבה מקובץ `.env`.
  - `pydantic` – מודלים לנתונים (ב-FastAPI זה מובנה).

## 8.2 Green API

- משמש כשכבת אינטגרציה ל-WhatsApp:
  - Webhooks להודעות נכנסות.
  - REST API לשליחת הודעות.
- קונפיגורציה:
  - `INSTANCE_ID` ו-`API_TOKEN`.
- בדיקות:
  - שליחת הודעות בדיקה.
  - צפייה בלוגים/console של Green API (אם קיים).

## 8.3 Supabase

- בסיס נתונים: Postgres מנוהל.
- פיצ'רים רלוונטיים:
  - REST API מובנה (PostgREST).
  - ספריית לקוח ל-Python.
  - Row Level Security (RLS).
  - ניהול גרסאות סכימה (Migrations) – מומלץ באמצעות כלי כמו `sqitch` / `dbmate` / Supabase migrations.

## 8.4 DevOps

- ניהול קוד:
  - Git (GitHub / GitLab / Azure DevOps / Bitbucket).
- CI/CD:
  - Pipeline אוטומטי לבנייה והרצת בדיקות.
  - פריסה לשרת בדיקות ואז ל-Production.
- Docker:
  - כתיבת `Dockerfile` ל-Bot Server.
  - ניהול קונפיגורציה באמצעות משתני סביבה.

## 8.5 ניטור ובקרה

- לוגים:
  - stdout/log files + רישום לוגים ב-Supabase (טבלת `bot_queries_log`).
- ניטור:
  - כלי ניטור ארגוני / פתרון ענן (Prometheus, Grafana, ELK, Application Insights וכו').
- Healthcheck:
  - Endpoint `GET /health` לבדיקת זמינות השירות.

