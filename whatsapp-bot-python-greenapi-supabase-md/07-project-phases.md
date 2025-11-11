# שלבי הפרויקט (Roadmap)

## שלב 1 – תשתית ו-Setup

- פתיחת פרויקט Supabase, הגדרת:
  - בסיס נתונים.
  - טבלאות בסיסיות (containers, ramp_operations, ships, bot_queries_log).
- הקמת פרויקט Python:
  - FastAPI/Flask.
  - הגדרת קובץ `requirements.txt`/`pyproject.toml`.
  - יצירת Route בסיסי (`/health`).

## שלב 2 – חיבור Green API ו-POC

- קונפיגורציה ב-Green API:
  - הגדרת Webhook לכתובת השרת.
  - בדיקת שליחת הודעות ידנית.
- מימוש Route `/api/green/webhook`:
  - קליטת הודעה.
  - החזרת תשובת echo למשתמש.
- בדיקת תרחיש WhatsApp ←→ Bot Server (ללא Supabase).

## שלב 3 – שילוב Supabase ו-Intent ראשון

- התקנת Supabase Python Client.
- כתיבת מודול `supabase_client.py`.
- מימוש Intent אחד לדוגמה:
  - "כמה מכולות היום?" → `get_daily_containers_count(date)`.
- שליחת תשובה אמיתית מה-DB ל-WhatsApp.

## שלב 4 – הרחבת Intents ושכלול NLU

- הוספת Intents נוספים (5–10):
  - סטטיסטיקות רמפה, סטטוס אוניות, לוקיישן מכולה וכו'.
- יצירת מודול Intent Engine:
  - התחלה ברגקס/מילון ביטויים.
  - בהמשך שילוב מודל LLM חיצוני/פנימי לשיפור ההבנה.
- טיפול בשגיאות ותרחישים חסרים:
  - תאריך חסר, מזהה שגוי וכו'.

## שלב 5 – Production

- הפרדת סביבות: dev / test / prod.
- הקשחת אבטחה:
  - ניהול מפתחות.
  - בדיקת חתימה מ-Green API.
  - עמידה במדיניות אבטחת מידע של הארגון.
- פריסה כקונטיינר (Docker) על שרת ייעודי/תשתית ענן.

## שלב 6 – שיפור מתמשך

- הרחבת מודל הנתונים וה-Intents.
- שיפור NLP/LLM להבנת שפה טבעית מורכבת.
- הוספת פיצ'רים:
  - פקודה להיסטוריית שאילתות.
  - אפשרות "לא מדויק, נסה שוב" והזנה חוזרת למודל.
- שילוב ערוצים נוספים (למשל Web Chat פנימי) שמשתמשים באותו Bot Server ו-Supabase.

