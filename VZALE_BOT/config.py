"""Common configuration loader for the bot and HTTP API.

Environment variables (can be placed in a .env file):
- BOT_TOKEN: Telegram bot token.
- DB_PATH: path to SQLite database file (default: tournament.db).
- API_SECRET: optional shared secret for future HTTP protection.
"""
import os
from dotenv import load_dotenv

# Load .env on import so both the bot and API share the same settings.
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "tournament.db")
API_SECRET = os.getenv("API_SECRET")
