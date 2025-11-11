# WhatsApp Operations Bot (Green API + Supabase)

This repository contains a FastAPI-based backend that connects WhatsApp via [Green API](https://green-api.com/en/docs/api/) and pulls organizational insights from Supabase, according to the project specification documents.

## Prerequisites

- Python 3.11+
- A configured Green API instance (`instanceId`, `apiToken`)
- Supabase project with the tables described in `whatsapp-bot-python-greenapi-supabase-md/05-supabase-schema.md`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env
# optional: copy credentials JSON template
cp config/supabase_credentials.example.json config/supabase_credentials.json

# prepare database tables
supabase db execute --file sql/create_containers_table.sql
supabase db execute --file sql/create_ramp_operations_table.sql
```

Update `.env` with real credentials.
If you plan to use Gemini analysis, set `GEMINI_API_KEY` (either in `.env` or `config/supabase_credentials.json`).

## Running Locally

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expose the local server (e.g., via ngrok) and configure the Green API webhook URL to `https://<public-url>/api/green/webhook`.

## Architecture Highlights

- `app/main.py`: FastAPI application bootstrap.
- `app/routes/webhook.py`: Receives Green API webhook notifications.
- `app/services/intent_engine.py`: Initial keyword-based intent detection.
- `app/services/supabase_client.py`: Supabase data access layer.
- `app/services/greenapi_client.py`: Outgoing WhatsApp messages through Green API.
- `app/services/gemini_client.py`: Bridges Supabase metrics to Google Gemini for AI-driven answers.
- `app/services/response_builder.py`: Formats textual replies.

The implementation aligns with the specification documents stored in `whatsapp-bot-python-greenapi-supabase-md/`.

## Database bootstrap

Create the `containers` table referenced by the CSV import:

```bash
supabase db execute --file sql/create_containers_table.sql
```

Create the `ramp_operations` table for vehicle statistics:

```bash
supabase db execute --file sql/create_ramp_operations_table.sql
```

Alternatively, run the contents of `sql/create_containers_table.sql` via the Supabase SQL editor.

## Deployment (Railway example)

1. Push the repository to GitHub (public or private).
2. Visit [Railway new project](https://railway.com/new) and choose “Deploy from GitHub”, selecting this repo.
3. After the service is created, open the **Variables** tab and add at minimum:
   - `GREEN_API_INSTANCE_ID`
   - `GREEN_API_TOKEN`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - Optional: `SUPABASE_SCHEMA`, `BOT_DISPLAY_NAME`, `GEMINI_API_KEY`
4. Railway uses Nixpacks or Docker automatically. ה-start command מוגדר בקובץ `railway.json` כ־
   ```
   sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
   ```
5. Deploy the service. Once the deployment is healthy, copy the public URL (e.g. `https://my-bot.up.railway.app`) and configure Green API’s webhook to:
   ```
   https://my-bot.up.railway.app/api/green/webhook
   ```

## Importing historical data

```bash
python3 -m scripts.upload_export_to_supabase --table containers
```

The script normalises Hebrew month names to ISO dates for `TARICH_PRIKA`.  
Populate `ramp_operations` using your operational data (vehicles per day/shift) to enable the vehicle count queries.

## Sending manual WhatsApp messages

Use the helper script to send a message via Green API:

```bash
python3 -m scripts.send_whatsapp_message --phone 050-4057453 --message "היי מאיר, הנה הקישור לבוט: https://example.com"
```

Add `--dry-run` to preview without sending. The script reads credentials from `.env` / `config/supabase_credentials.json`.

## Supported bot queries

- Daily containers: “כמה מכולות היום?”
- Container range: “כמה מכולות נפרקו מתאריך 01/01/2023 עד תאריך 31/01/2023?”
- Vehicle range: “כמה רכבים היו בין 01/01/2023 ל-15/01/2023?”
- Free-form analysis (requires `GEMINI_API_KEY`): “נתח באמצעות גמיני את תפוקת המכולות בחודש האחרון.”

All date expressions should use `dd/mm/yyyy` (or `dd-mm-yyyy`) format.

# whatsapp-greenapi-supabase-bot
# whatsapp-greenapi-supabase-bot
