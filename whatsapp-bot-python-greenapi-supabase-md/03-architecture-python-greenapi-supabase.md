# ארכיטקטורה לוגית – Python + Green API + Supabase

## מבט כללי

המערכת מורכבת משלושה רכיבים עיקריים:

1. **Green API** – שכבת WhatsApp Gateway:
   - מקבלת הודעות מ-WhatsApp.
   - שולחת Webhook לשירות ה-Python.
   - מאפשרת שליחת הודעות חזרה למשתמשים.

2. **Python Bot Server** – לוגיקה עסקית ו-AI Orchestrator:
   - כתוב ב-Python (FastAPI/Flask).
   - מקבל Webhook מ-Green API.
   - מנתח את ההודעה (NLU/LLM).
   - יוצר שאילתות ל-Supabase.
   - בונה תשובת טקסט ושולח דרך Green API.

3. **Supabase** – שכבת נתונים:
   - Postgres מנוהל בענן.
   - טבלאות/Views לנתונים תפעוליים וסטטיסטיים.
   - טבלת לוג שאלות ותשובות.
   - שימוש ב-RLS ותפקידי שירות (service role) לצד השרת.

## 3.1 זרימת מידע טיפוסית

1. משתמש שולח הודעת WhatsApp לבוט.
2. Green API מקבל את ההודעה ושולח בקשת Webhook (HTTP POST) לכתובת ה-Python Bot Server.
3. Python Bot Server:
   - קורא את גוף הבקשה (JSON).
   - מוציא מזהה משתמש, טקסט הודעה, מועד שליחה.
   - מניע מודול Intent/NLU שזיהה את סוג השאלה והפרמטרים.
   - בונה שאילתה (SQL/REST) ל-Supabase באמצעות Supabase Python Client.
   - מקבל תוצאות, מעבד אותן ומנסח תשובה טקסטואלית.
4. הבוט שולח בקשת HTTP ל-Green API לשליחת הודעת WhatsApp חזרה למשתמש עם הטקסט שנבנה.
5. במקביל, הבוט יכול לרשום את השיחה (שאלה/תשובה) לטבלת לוג ב-Supabase.

## 3.2 רכיבי תוכנה ב-Python Bot Server

- `main.py` – נקודת כניסה ל-FastAPI/Flask.
- `routes/webhook.py` – Route שמקבל Webhook מ-Green API.
- `services/intent_engine.py` – ניתוח טקסט וזיהוי Intent (בהתחלה חוקים פשוטים, בהמשך LLM).
- `services/supabase_client.py` – עטיפה סביב Supabase Python Client לביצוע שאילתות.
- `services/greenapi_client.py` – שליחת הודעות ל-Green API.
- `services/response_builder.py` – בניית טקסט תשובה ידידותי.
- `models/` – מודלים לייצוג תוצאות DB ו-DTOs של ה-Webhooks.

## 3.3 דפוס עבודה

- השירות יהיה Stateless ככל האפשר (ללא Session פנימי).
- כל state מתמשך (log שיחות, תוצאות, cache) – יישב ב-Supabase או ברכיב cache חיצוני (Redis) אם יוחלט.
