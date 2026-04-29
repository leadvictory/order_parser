import json
import re
import csv
import ssl
import smtplib
from pathlib import Path
from email.header import decode_header
from email.utils import parseaddr, formataddr, make_msgid
from email.mime.text import MIMEText

from config import (
    PROCESSED_FILE,
    USERS_CSV,
    SMTP_SERVER,
    SMTP_PORT,
    GMAIL_USER,
    GMAIL_APP_PASSWORD,
)


def load_processed_uids():
    if PROCESSED_FILE.exists():
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_processed_uids(uids):
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(uids)), f, indent=2)


def decode_mime_words(value):
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def sanitize_filename(filename):
    if not filename:
        return "unknown_attachment"
    keep = "-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    cleaned = "".join(c if c in keep else "_" for c in filename)
    return cleaned.strip() or "unknown_attachment"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def extract_email_body(msg):
    text_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", "")).lower()

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    text_parts.append(payload.decode(charset, errors="replace"))
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            text_parts.append(payload.decode(charset, errors="replace"))

    return "\n".join(text_parts).strip()


def extract_login_id(subject, body=""):
    candidates = [subject or "", body or ""]

    patterns = [
        r"\bSW\s+Login\s+([A-Za-z0-9_-]+)\b",
        r"\bLogin\s+([A-Za-z0-9_-]+)\b",
        r"\b([0-9]{4,}[A-Za-z]{2,})\b",
    ]

    for text in candidates:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

    return None


def find_password_for_login(login_id, csv_path=USERS_CSV):
    if not login_id:
        return None

    if not csv_path.exists():
        print(f"Users CSV not found: {csv_path}")
        return None

    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("Users CSV has no headers.")
                return None

            login_field = "id_webuser"
            password_field = "passwd_webuser"

            for row in reader:
                row_login = str(row.get(login_field, "")).strip()
                row_password = str(row.get(password_field, "")).strip()

                if row_login.lower() == login_id.lower():
                    return row_password or None

    except Exception as e:
        print(f"Error reading users CSV: {e}")
        return None

    return None


def build_reply_subject(original_subject):
    original_subject = original_subject or ""
    if original_subject.lower().startswith("re:"):
        return original_subject
    return f"Re: {original_subject}"


def send_reply_email(original_msg, success, reason, login_id=None, items=None):
    _, from_email = parseaddr(original_msg.get("From", ""))
    if not from_email:
        print("Reply skipped: original sender email not found.")
        return False

    original_subject = decode_mime_words(original_msg.get("Subject", ""))
    subject = build_reply_subject(original_subject)
    item_count = len(items or [])

    if success:
        body = (
            f"Hello,\n\n"
            f"Your order upload was completed successfully.\n\n"
            f"Login ID: {login_id or 'N/A'}\n"
            f"Items parsed: {item_count}\n\n"
            f"Status: SUCCESS\n\n"
            f"Regards"
        )
    else:
        body = (
            f"Hello,\n\n"
            f"Your order upload could not be completed.\n\n"
            f"Login ID: {login_id or 'N/A'}\n"
            f"Items parsed: {item_count}\n"
            f"Status: FAILED\n"
            f"Reason: {reason}\n\n"
            f"Regards"
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Order Automation", GMAIL_USER))
    msg["To"] = from_email

    original_message_id = original_msg.get("Message-ID")
    if original_message_id:
        msg["In-Reply-To"] = original_message_id
        existing_refs = original_msg.get("References", "").strip()
        msg["References"] = f"{existing_refs} {original_message_id}".strip()
    else:
        msg["Message-ID"] = make_msgid()

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [from_email], msg.as_string())
        print(f"Reply sent to: {from_email}")
        return True
    except Exception as e:
        print(f"Failed to send reply email: {e}")
        return False