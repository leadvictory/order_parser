import time

from config import SAVE_DIR, OUTPUT_DIR, POLL_INTERVAL
from imap_client import connect_imap, fetch_unread_message_uids, fetch_message, download_attachments_from_message
from email_utils import (
    load_processed_uids,
    save_processed_uids,
    decode_mime_words,
    extract_email_body,
    extract_login_id,
    find_password_for_login,
    send_reply_email,
)
from parser_utils import extract_sku_quantity_pairs, extract_order_number, extract_shipping_fields
from order_service import save_login_json, upload_saved_order


def process_message(mail, uid):
    msg = fetch_message(mail, uid)
    if not msg:
        print(f"Failed to fetch UID={uid}")
        return False

    subject = decode_mime_words(msg.get("Subject", ""))
    from_addr = decode_mime_words(msg.get("From", ""))
    body = extract_email_body(msg)

    print(f"\nProcessing email UID={uid}")
    print(f"From: {from_addr}")
    print(f"Subject: {subject}")

    login_id = extract_login_id(subject, body)
    order_number = extract_order_number(body)
    shipping = extract_shipping_fields(body)

    print(f"Extracted order_number: {order_number}")
    print(f"Extracted address1: {shipping['address1']}")
    print(f"Extracted city: {shipping['city']}")
    print(f"Extracted state: {shipping['state']}")
    print(f"Extracted zip: {shipping['zip']}")
    items = extract_sku_quantity_pairs(body)
    password = find_password_for_login(login_id)

    print(f"Extracted login_id: {login_id}")
    print(f"Extracted items: {len(items)}")
    print(f"Password found: {'YES' if password else 'NO'}")

    if not login_id:
        reason = "Login ID not found in subject or body."
        print(reason)
        send_reply_email(msg, False, reason, login_id=login_id, items=items)
        return True

    if not items:
        reason = "No SKU/quantity pairs were found in the email body."
        print(reason)
        send_reply_email(msg, False, reason, login_id=login_id, items=items)
        return True

    if not password:
        reason = f"Password not found in Users.csv for login ID '{login_id}'."
        print(reason)
        send_reply_email(msg, False, reason, login_id=login_id, items=items)
        return True

    output_path = save_login_json(
        login_id=login_id,
        password=password,
        order_number=order_number,
        sku_quantity_pairs=items,
        subject=subject,
        from_addr=from_addr,
        email_uid=uid,
        address1=shipping["address1"],
        city=shipping["city"],
        state=shipping["state"],
        zip_code=shipping["zip"],
    )
    print(f"Saved parsed JSON: {output_path}")

    upload_ok, upload_reason = upload_saved_order(output_path)
    print(f"Upload status: {'SUCCESS' if upload_ok else 'FAILED'}")
    print(f"Upload reason: {upload_reason}")

    send_reply_email(
        original_msg=msg,
        success=upload_ok,
        reason=upload_reason,
        login_id=login_id,
        items=items,
    )

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
                time.sleep(0.1)
                # print("\nNo unread emails found.")

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