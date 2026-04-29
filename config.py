from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

SAVE_DIR = Path(os.getenv("SAVE_DIR", "downloaded_attachments"))
PROCESSED_FILE = Path(os.getenv("PROCESSED_FILE", "processed_uids.json"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "orders/pending"))
USERS_CSV = Path(os.getenv("USERS_CSV", "Users.csv"))

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
FILTER_FROM_EMAIL = os.getenv("FILTER_FROM_EMAIL", "jdopson@stevenwillandinc.com")

ALLOWED_EXTENSIONS = {".pdf", ".xls", ".xlsx", ".xlsm", ".csv"}