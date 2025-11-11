# מבנה נתונים ב-Supabase

## 5.1 עקרונות כלליים

- Supabase משמש:
  - כמקור נתונים תפעולי/סטטיסטי לשאלות המשתמשים.
  - כמאגר לוגים של השיחות והשימוש בבוט.
- מסד הנתונים מבוסס Postgres.
- שימוש ב-RLS (Row Level Security) מופעל כברירת מחדל, כאשר הבוט עובד עם Service Role Key מצד השרת.

## 5.2 טבלאות לדוגמה

> השמות והמבנה יותאמו למציאות בארגון, אבל זה שלד ראשוני.

### טבלת מכולות – `containers`

- `id` (PK, text) – מספר מכולה.
- `status` (text) – מצב נוכחי (in_port, loaded, delivered, damaged וכו').
- `last_location` (text) – מיקום אחרון ידוע.
- `last_operation_time` (timestamp) – מועד פעולה אחרונה.
- שדות נוספים: סוג מכולה, גודל, לקוח וכו'.

### טבלת פעולות רמפה – `ramp_operations`

- `id` (PK, serial/bigint).
- `ramp_id` (text/int).
- `datetime` (timestamp).
- `operation_type` (text) – load/unload.
- `containers_count` (int).
- `vehicles_count` (int).
- `shift` (text) – morning/noon/night.

### טבלת אוניות – `ships`

- `id` (PK).
- `name` (text).
- `status` (text) – arrived/berthed/departed וכו'.
- `eta` (timestamp).
- שדות נוספים לפי הצורך.

### טבלת לוג שאלות – `bot_queries_log`

- `id` (PK, serial/bigint).
- `user_phone` (text).
- `user_text` (text).
- `intent` (text).
- `parameters` (jsonb) – פרמטרים שאותרו מהטקסט (תאריכים, מזהים וכו').
- `response_text` (text).
- `created_at` (timestamp, default now()).

## 5.3 גישה מ-Python

- שימוש ב-Supabase Python Client (`supabase-py`):
  - הפעלת קונפיגורציה עם `SUPABASE_URL` ו-`SUPABASE_SERVICE_ROLE_KEY`.
- פונקציות שירות לדוגמה:
  - `get_daily_containers_count(date)` – מחזירה מספר.
  - `get_ramp_stats(ramp_id, date, shift)` – מחזירה אובייקט/רשומה.
  - `get_container_location(container_id)` – מחזירה פרטי מכולה.
  - `log_query(user_phone, user_text, intent, parameters, response_text)` – רושמת לוג.

