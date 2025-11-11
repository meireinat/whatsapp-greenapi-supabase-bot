# אינטגרציה עם Green API

## 4.1 Webhook נכנס (Incoming Messages)

### הגדרות ב-Green API

- הגדרת כתובת Webhook לכתובת ה-Python Bot Server, לדוגמה:
  - `https://bot.myorg.local/api/green/webhook`
- קביעת סוגי האירועים שיישלחו (הודעות טקסט נכנסות, סטטוסים וכו').

### התנהגות בצד ה-Python

Route לדוגמה (FastAPI):

- `POST /api/green/webhook`

לוגיקה:

1. אימות מקור הבקשה (לפי Token/Signature אם זמין).
2. פריסת גוף ה-JSON:
   - מזהה משתמש (מספר טלפון / chatId).
   - טקסט ההודעה.
   - תאריך/שעה.
3. קריאה ל-Intent Engine לזיהוי:
   - Intent (לדוגמה: `daily_containers_count`, `container_location`).
   - פרמטרים (תאריך, מזהה מכולה וכו').
4. שליחת בקשה ל-Supabase לקבלת הנתונים.
5. בניית טקסט תשובה ושליחה חזרה ל-Green API (ראו סעיף 4.2).

## 4.2 שליחת הודעות חזרה (Outgoing Messages)

### קריאה ל-Green API

- שימוש ב-REST API של Green API לסוגי קריאות כמו:
  - `sendMessage` / `sendText` (בהתאם לדוקומנטציה).
- כתובת לדוגמה (מבוסס instanceId ו-apiToken):
  - `https://api.green-api.com/waInstance{INSTANCE_ID}/sendMessage/{API_TOKEN}`

### לוגיקה בצד ה-Python

פונקציה לדוגמה:

- `send_whatsapp_message(phone: str, text: str)`

צעדים:

1. בניית גוף JSON לפי דרישות Green API (כולל chatId/phone, טקסט הודעה).
2. ביצוע בקשת HTTP (באמצעות `requests`/`httpx`).
3. טיפול בשגיאות (timeout, שגיאות HTTP, שגיאות אפליקטיביות מ-Green API).
4. החזרת סטטוס לשכבת ה-Bot (לוג/ניטור).

## 4.3 בדיקות ואימות

- בדיקת Webhook:
  - קבלת הודעת בדיקה מ-Green API.
  - החזרת תשובת echo למשתמש ("קיבלתי את ההודעה: ...").
- בדיקת תרחיש מלא:
  - הודעת WhatsApp → Webhook → Python → Supabase → Python → Green API → תשובה למכשיר.
