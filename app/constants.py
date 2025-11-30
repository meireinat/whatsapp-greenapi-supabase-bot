"""
Application constants and version information.
"""

# Application version
VERSION = "0.1.0"

# Application name
APP_NAME = "WhatsApp Operations Bot"

# Default bot display name
DEFAULT_BOT_DISPLAY_NAME = "Operations Bot"

# API endpoints
HEALTH_ENDPOINT = "/health"
WEBHOOK_ENDPOINT = "/api/green/webhook"

# Service configuration
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_COUNCIL_MODELS = [
    "openai/gpt-4o",
    "google/gemini-2.0-flash-exp",
    "anthropic/claude-3.5-sonnet",
]
DEFAULT_CHAIRMAN_MODEL = "google/gemini-2.0-flash-exp"

# Conversation history settings
MAX_CONVERSATION_HISTORY = 5  # Maximum number of previous queries to retrieve

# Data fetching settings
DEFAULT_METRICS_YEARS_BACK = 5  # Years of historical data to fetch for LLM analysis
DEFAULT_MAX_ROWS_FOR_LLM = 10000  # Maximum rows to fetch for LLM analysis



