# Knowledge Files Directory

Place your knowledge files in this directory. The topic/subject will be automatically extracted from the filename.

## Supported File Types
- `.txt` - Plain text files
- `.md` - Markdown files
- `.json` - JSON files
- `.csv` - CSV files

## Naming Convention
The topic is extracted from the filename (without extension). For example:
- `מכולות_סטטוס.txt` → Topic: "מכולות סטטוס"
- `תקנות_נמל.pdf` → Topic: "תקנות נמל"
- `container-status.txt` → Topic: "container status"

## How It Works
1. Files are automatically loaded when the bot starts
2. Each file is split into chunks (approximately 1000 characters each)
3. When a user asks a question, the bot searches for relevant sections based on:
   - Keyword matching in the query
   - Topic name matching (files with matching topic names get higher priority)
4. Relevant sections are included in the LLM context to provide accurate answers

## File Encoding
The bot supports multiple encodings:
- UTF-8 (preferred)
- Windows-1255 (CP1255)
- ISO-8859-8
- Latin-1

If a file cannot be decoded, it will be skipped with a warning in the logs.

