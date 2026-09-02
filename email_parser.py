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
from parser_utils import (
    extract_sku_quantity_pairs,
    extract_order_number,
    extract_shipping_fields,
    extract_terms,
    extract_freight,
    extract_type,
    extract_ship_to,
    extract_ship_via,
)
from order_service import save_login_json, upload_saved_order
import os
from parser import extract_po_data
from pdf_parser import extract_order_details

def parse_attachment_data(file_path):
    """
    Use existing parsers based on file extension.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in {".xls", ".xlsx", ".xlsm", ".csv"}:
        return extract_po_data(file_path)

    if ext == ".pdf":
        return extract_order_details(file_path)

    return None


def merge_order_data(body_data, attachment_data):
    """
    Prefer attachment data when present, otherwise keep body data.
    """
    if not attachment_data:
        return body_data

    return {
        "order_number": attachment_data.get("order_number") or body_data.get("order_number") or "By email",
        "customer_name": attachment_data.get("customer_name") or body_data.get("customer_name") or "",
        "address1": attachment_data.get("address1") or body_data.get("address1"),
        "city": attachment_data.get("city") or body_data.get("city"),
        "state": attachment_data.get("state") or body_data.get("state"),
        "zip": attachment_data.get("zip") or body_data.get("zip"),
        "country": attachment_data.get("country") or body_data.get("country") or "United States",
        "order_lines": attachment_data.get("order_lines") or body_data.get("order_lines") or [],
    }

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
    password = find_password_for_login(login_id)

    # Parse from email body first
    order_number = extract_order_number(body)
    terms = extract_terms(body)
    freight = extract_freight(body)
    order_type = extract_type(body)
    ship_to = extract_ship_to(body)
    ship_via = extract_ship_via(body)
    shipping = extract_shipping_fields(body)
    body_items = extract_sku_quantity_pairs(body)

    body_data = {
        "order_number": order_number or "By email",
        "account_id": login_id,
        "terms": terms,
        "freight": freight,
        "order_type": order_type,
        "ship_to": ship_to,
        "ship_via": ship_via,
        "customer_name": "",
        "address1": shipping["address1"],
        "city": shipping["city"],
        "state": shipping["state"],
        "zip": shipping["zip"],
        "country": "United States",
        "order_lines": body_items,
    }

    print(f"Extracted login_id: {login_id}")
    print(f"Body order_number: {body_data['order_number']}")
    print(f"Terms: {terms}")
    print(f"Type: {order_type}")
    print(f"Freight: {freight}")
    print(f"ShipTo: {ship_to}")
    print(f"ShipVia: {ship_via}")
    print(f"Body address1: {body_data['address1']}")
    print(f"Body city: {body_data['city']}")
    print(f"Body state: {body_data['state']}")
    print(f"Body zip: {body_data['zip']}")
    print(f"Body items: {len(body_items)}")
    print(f"Password found: {'YES' if password else 'NO'}")

    # Download attachments and try to parse them
    saved_attachments = download_attachments_from_message(mail, uid)
    attachment_data = None

    if saved_attachments:
        print(f"Downloaded {len(saved_attachments)} attachment(s).")

        for full_path in saved_attachments:
            try:
                parsed = parse_attachment_data(full_path)
                if parsed:
                    print(f"Attachment parsed successfully: {full_path}")
                    print(f"Attachment order_number: {parsed.get('order_number')}")
                    print(f"Attachment items: {len(parsed.get('order_lines', []))}")

                    # Prefer first attachment with usable order lines
                    if parsed.get("order_lines"):
                        attachment_data = parsed
                        break
            except Exception as e:
                print(f"Attachment parse failed for {full_path}: {e}")
    else:
        print("No matching attachments found.")

    final_data = merge_order_data(body_data, attachment_data)

    print(f"Final order_number: {final_data['order_number']}")
    print(f"Final address1: {final_data['address1']}")
    print(f"Final city: {final_data['city']}")
    print(f"Final state: {final_data['state']}")
    print(f"Final zip: {final_data['zip']}")
    print(f"Final items: {len(final_data['order_lines'])}")
    # time.sleep(1000)
    if not login_id:
        reason = "Login ID not found in subject or body."
        print(reason)
        return True

    if not final_data["order_lines"]:
        reason = "No SKU/quantity pairs were found in the email body or attachments."
        print(reason)
        send_reply_email(msg, False, reason, login_id=login_id, items=[])
        return True

    if not password:
        reason = f"Password not found in Users.csv for login ID '{login_id}'."
        print(reason)
        send_reply_email(msg, False, reason, login_id=login_id, items=final_data["order_lines"])
        return True
    print("here")
    output_path = save_login_json(
        login_id=login_id,
        password=password,
        order_number=final_data.get("order_number"),
        terms=final_data.get("terms", ""),
        order_type=final_data.get("order_type", ""),
        freight=final_data.get("freight", ""),
        ship_to=final_data.get("ship_to", ""),
        ship_via=final_data.get("ship_via", ""),
        sku_quantity_pairs=final_data.get("order_lines", []),
        subject=subject,
        from_addr=from_addr,
        email_uid=uid,
        address1=final_data.get("address1"),
        city=final_data.get("city"),
        state=final_data.get("state"),
        zip_code=final_data.get("zip"),
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
        items=final_data["order_lines"],
    )

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