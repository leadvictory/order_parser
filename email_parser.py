import imaplib
import email
from email.header import decode_header
import json
import time
import csv
import re
from pathlib import Path
from swi import extract_credentials_from_filename, upload_order
# =========================
# CONFIG
# =========================
GMAIL_USER = "intelliresponse911@gmail.com"
GMAIL_APP_PASSWORD = "mubs olnn ejzz haww"
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

SAVE_DIR = Path("downloaded_attachments")
PROCESSED_FILE = Path("processed_uids.json")
OUTPUT_DIR = Path("orders/pending")
USERS_CSV = Path("Users.csv")

ALLOWED_EXTENSIONS = {".pdf", ".xls", ".xlsx", ".xlsm", ".csv"}
POLL_INTERVAL = 30


# =========================
# HELPERS
# =========================
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
    """
    Get the best plain-text body from the email.
    """
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
    """
    Extract login id from subject/body.
    Example:
      SW Login 376650swi
    """
    candidates = [subject or "", body or ""]

    patterns = [
        r"\bSW\s+Login\s+([A-Za-z0-9_-]+)\b",
        r"\bLogin\s+([A-Za-z0-9_-]+)\b",
        r"\b([0-9]{4,}[A-Za-z]{2,})\b",  # catches things like 376650swi
    ]

    for text in candidates:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

    return None


import re

def extract_sku_quantity_pairs(body):
    """
    Extract SKU and quantity pairs from email body.

    Supports bodies like:

    Please order the following:

    Precision Saw, West Warwick, RI

    Sku                            Quantity
    511010601          12
    588049602          12
    BCZ230TS           12
    BCZ265S             6
    """

    pairs = []
    in_items_section = False

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Normalize spaces/tabs
        line = re.sub(r"\s+", " ", line)

        # Detect the header row
        if re.search(r"\bsku\b", line, re.IGNORECASE) and re.search(r"\bquantity\b", line, re.IGNORECASE):
            in_items_section = True
            continue

        # Ignore everything before the header
        if not in_items_section:
            continue

        # Match: SKU + quantity
        # SKU can be numeric or alphanumeric like BCZ230TS
        match = re.match(r"^([A-Z0-9]+)\s+(\d+)$", line, re.IGNORECASE)
        if match:
            sku = match.group(1).upper()
            quantity = int(match.group(2))
            pairs.append({"sku": sku, "quantity": quantity})
        else:
            # Optional: stop if section ends and another text block starts
            # break
            pass

    return pairs


def find_password_for_login(login_id, csv_path=USERS_CSV):
    """
    Look up password from web users.csv

    Expected headers can include:
      Login ID, Password, Dealer Id, Ship To ID, email
    """
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

            # Normalize header lookup
            normalized_fields = {
                field.strip().lower().replace("_", " "): field
                for field in reader.fieldnames
            }

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

def save_login_json(login_id, password, sku_quantity_pairs, subject, from_addr, email_uid):
    """
    Save parsed data into:
      <login_id>_password_time.json
    """
    if not login_id:
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / f"{login_id}___{password}___time.json"

    payload = {
        "login_id": login_id,
        "password": password,
        "order_number": "By email",
        "order_lines": sku_quantity_pairs,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_path


# =========================
# GMAIL LOGIC
# =========================
def connect_imap():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    return mail


def fetch_unread_message_uids(mail):
    mail.select("INBOX")

    search_criteria = '(UNSEEN FROM "jdopson@stevenwillandinc.com")'
    status, data = mail.uid("search", None, search_criteria)

    if status != "OK":
        return []

    raw = data[0].decode().strip()
    return raw.split() if raw else []


def download_attachments_from_message(mail, uid):
    saved_files = []

    status, data = mail.uid("fetch", uid, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        return saved_files

    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()

        if not filename:
            continue

        filename = decode_mime_words(filename)
        filename = sanitize_filename(filename)
        ext = Path(filename).suffix.lower()

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


def process_message(mail, uid):
    """
    Parse one email:
    - subject
    - body
    - login_id
    - sku/quantity pairs
    - password from web users.csv
    - save json
    """
    status, data = mail.uid("fetch", uid, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        print(f"Failed to fetch UID={uid}")
        return False

    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = decode_mime_words(msg.get("Subject", ""))
    from_addr = decode_mime_words(msg.get("From", ""))
    body = extract_email_body(msg)

    print(f"\nProcessing email UID={uid}")
    print(f"From: {from_addr}")
    print(f"Subject: {subject}")

    login_id = extract_login_id(subject, body)
    items = extract_sku_quantity_pairs(body)
    password = find_password_for_login(login_id)

    print(f"Extracted login_id: {login_id}")
    print(f"Extracted items: {len(items)}")
    print(f"Password found: {'YES' if password else 'NO'}")

    output_path = None
    if login_id:
        output_path = save_login_json(
            login_id=login_id,
            password=password,
            sku_quantity_pairs=items,
            subject=subject,
            from_addr=from_addr,
            email_uid=uid,
        )
        print(f"Saved parsed JSON: {output_path}")
    else:
        print("No login_id found. JSON not saved.")

    saved_attachments = download_attachments_from_message(mail, uid)
    if saved_attachments:
        print(f"Downloaded {len(saved_attachments)} attachment(s).")
    else:
        print("No matching attachments found.")

    return True


def main():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    processed_uids = load_processed_uids()

    print("Starting Gmail watcher...")

    while True:
        mail = None
        try:
            mail = connect_imap()
            unread_uids = fetch_unread_message_uids(mail)

            if unread_uids:
                print(f"\nFound {len(unread_uids)} unread email(s).")
            else:
                print("\nNo unread emails found.")

            for uid in unread_uids:
                if uid in processed_uids:
                    continue

                process_message(mail, uid)

                processed_uids.add(uid)
                save_processed_uids(processed_uids)

            mail.logout()

        except KeyboardInterrupt:
            print("\nStopped by user.")
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
            break

        except Exception as e:
            print(f"\nError: {e}")
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()