import imaplib
import email

from config import (
    IMAP_SERVER,
    IMAP_PORT,
    GMAIL_USER,
    GMAIL_APP_PASSWORD,
    SAVE_DIR,
    ALLOWED_EXTENSIONS,
    FILTER_FROM_EMAIL,
)
from email_utils import decode_mime_words, sanitize_filename, unique_path


def connect_imap():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    return mail


def fetch_unread_message_uids(mail):
    mail.select("INBOX")
    search_criteria = f'(UNSEEN FROM "{FILTER_FROM_EMAIL}")'
    status, data = mail.uid("search", None, search_criteria)

    if status != "OK":
        return []

    raw = data[0].decode().strip()
    return raw.split() if raw else []


def fetch_message(mail, uid):
    status, data = mail.uid("fetch", uid, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        return None

    raw_email = data[0][1]
    return email.message_from_bytes(raw_email)


def download_attachments_from_message(mail, uid):
    saved_files = []

    msg = fetch_message(mail, uid)
    if not msg:
        return saved_files

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()

        if not filename:
            continue

        filename = decode_mime_words(filename)
        filename = sanitize_filename(filename)
        ext = filename.lower().rsplit(".", 1)
        ext = f".{ext[-1]}" if len(ext) > 1 else ""

        if ext not in ALLOWED_EXTENSIONS:
            continue

        if "attachment" not in content_disposition.lower() and "inline" not in content_disposition.lower():
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        SAVE_DIR.mkdir(parents=True, exist_ok=True)

        output_path = unique_path(SAVE_DIR / filename)
        with open(output_path, "wb") as f:
            f.write(payload)

        saved_files.append(str(output_path))
        print(f"Saved attachment: {output_path}")

    return saved_files