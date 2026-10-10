"""Central config. Secrets come from .env only. Legal parameters live in rules/delay_rules.json."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "rules" / "delay_rules.json"
SAMPLE_DATA_PATH = ROOT / "data" / "sample_records.json"
DB_PATH = os.getenv("DB_PATH") or str(ROOT / "kaamkahisab.db")
AS_OF_DATE = os.getenv("AS_OF_DATE") or None      # "YYYY-MM-DD" to freeze "today" for demos/tests

SUPPORTED_LANGS = ["hi", "en"]                    # add a language: add its dict in messages.py + here
DEFAULT_LANG = "en"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
