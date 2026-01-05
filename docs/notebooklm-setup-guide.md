# מדריך הגדרה - התחברות ל-NotebookLM Enterprise

## דרישות מוקדמות

כדי להתחבר ל-NotebookLM Enterprise API, אתה צריך:

### 1. Google Cloud Project עם NotebookLM Enterprise

1. **הפעל NotebookLM Enterprise בפרויקט שלך:**
   - לך ל-[Google Cloud Console](https://console.cloud.google.com)
   - בחר את הפרויקט שלך
   - הפעל את NotebookLM Enterprise API
   - ודא שיש לך הרשאות מתאימות

2. **קבל את Project Number:**
   - ב-Google Cloud Console, בפרויקט שלך
   - Project Number מופיע בדף Overview
   - זה מספר (לא שם הפרויקט)

### 2. Authentication (אימות)

יש שתי דרכים להתחבר:

#### אופציה A: שימוש ב-gcloud CLI (מומלץ לפיתוח מקומי)

```bash
# התחבר ל-Google Cloud
gcloud auth login --enable-gdrive-access

# ודא שיש לך את ההרשאות הנכונות
gcloud auth application-default login
```

הקוד ינסה להשתמש ב-`gcloud auth print-access-token` אוטומטית.

#### אופציה B: שימוש ב-API Key או Service Account

1. **צור Service Account:**
   ```bash
   gcloud iam service-accounts create notebooklm-service \
       --display-name="NotebookLM Service Account"
   ```

2. **הענק הרשאות:**
   ```bash
   gcloud projects add-iam-policy-binding PROJECT_NUMBER \
       --member="serviceAccount:notebooklm-service@PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/discoveryengine.editor"
   ```

3. **צור JSON key:**
   ```bash
   gcloud iam service-accounts keys create notebooklm-key.json \
       --iam-account=notebooklm-service@PROJECT_ID.iam.gserviceaccount.com
   ```

4. **הגדר משתנה סביבה:**
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/notebooklm-key.json"
   ```

### 3. משתני סביבה ב-Railway

הגדר את המשתנים הבאים ב-Railway:

#### חובה:
- `GOOGLE_CLOUD_PROJECT_NUMBER` - מספר הפרויקט (מספר, לא שם)
  - דוגמה: `123456789012`

#### אופציונלי (יש defaults):
- `NOTEBOOKLM_NOTEBOOK_ID` - מזהה ה-Notebook
  - אם לא מוגדר, ישתמש ב-default: `66688b34-ca77-4097-8ac8-42ca8285681f`
  - ניתן למצוא ב-URL של ה-Notebook: `https://notebooklm.google.com/notebook/NOTEBOOK_ID`

- `NOTEBOOKLM_LOCATION` - מיקום גיאוגרפי
  - Default: `global`
  - אפשרויות: `global`, `us`, `eu`

- `NOTEBOOKLM_ENDPOINT_LOCATION` - מיקום ה-API endpoint
  - Default: `global`
  - אפשרויות: `global`, `us-`, `eu-`

#### אופציונלי (אם יש):
- `GEMINI_API_KEY` - אם יש לך Gemini API key, הוא יכול לשמש כ-access token
  - לא חובה, אבל יכול לעזור

### 4. יצירת Notebook (אם עדיין לא קיים)

אם אתה צריך ליצור Notebook חדש:

1. לך ל-[NotebookLM](https://notebooklm.google.com)
2. צור Notebook חדש
3. העתק את ה-Notebook ID מה-URL
4. הגדר אותו ב-`NOTEBOOKLM_NOTEBOOK_ID`

## בדיקת החיבור

לאחר ההגדרה, תוכל לבדוק אם החיבור עובד:

1. שאל שאלה שאין עליה תשובה בקבצים המקומיים
2. הבוט אמור לנסות להתחבר ל-NotebookLM Enterprise API
3. אם זה עובד, תקבל תשובה מה-NotebookLM
4. אם לא, תקבל הודעה עם קישור לבדיקה ידנית

## פתרון בעיות

### שגיאת Authentication
- ודא ש-`gcloud auth login` בוצע
- או הגדר `GOOGLE_APPLICATION_CREDENTIALS` עם Service Account key

### שגיאת Project Number
- ודא שהגדרת `GOOGLE_CLOUD_PROJECT_NUMBER` עם המספר הנכון
- זה לא שם הפרויקט, אלא המספר

### שגיאת Notebook ID
- ודא שה-Notebook ID נכון
- ודא שיש לך גישה ל-Notebook הזה

### שגיאת API לא פעיל
- ודא ש-NotebookLM Enterprise API מופעל בפרויקט
- לך ל-Google Cloud Console > APIs & Services > Enabled APIs
- חפש "Discovery Engine API" או "NotebookLM Enterprise API"

## דוגמה להגדרה מלאה ב-Railway

```
GOOGLE_CLOUD_PROJECT_NUMBER=123456789012
NOTEBOOKLM_NOTEBOOK_ID=66688b34-ca77-4097-8ac8-42ca8285681f
NOTEBOOKLM_LOCATION=global
NOTEBOOKLM_ENDPOINT_LOCATION=global
GEMINI_API_KEY=your-gemini-api-key (אופציונלי)
```

## הערות חשובות

1. **NotebookLM Enterprise** דורש הרשאות מיוחדות - ודא שיש לך גישה
2. **Project Number** הוא מספר, לא שם - חשוב מאוד!
3. **Authentication** יכול להיות דרך gcloud או Service Account
4. אם אין גישה ל-Enterprise API, הבוט יחזור ל-fallback עם הפניה ידנית

