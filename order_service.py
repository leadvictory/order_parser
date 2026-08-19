import json
from pathlib import Path

from config import OUTPUT_DIR
from swi import extract_credentials_from_filename, upload_order


def save_login_json(
    login_id,
    password,
    order_number,
    terms, 
    order_type,
    freight,
    ship_to,
    ship_via,
    sku_quantity_pairs,
    subject,
    from_addr,
    email_uid,
    address1=None,
    city=None,
    state=None,
    zip_code=None,
):
    """
    Save parsed data into:
      <login_id>___<password>___time.json
    """
    if not login_id:
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_password = password if password else "NO_PASSWORD"
    final_order_number = order_number or "By email"

    output_path = OUTPUT_DIR / f"{login_id}___{safe_password}___time.json"
    print(output_path)
    payload = {
        "login_id": login_id,
        "password": password,
        "order_number": final_order_number,
        "terms": terms,
        "order_type": order_type,
        "freight": freight,
        "ship_to": ship_to,
        "ship_via": ship_via,
        "address1": address1,
        "city": city,
        "state": state,
        "zip": zip_code,
        "order_lines": sku_quantity_pairs,
        "subject": subject,
        "from": from_addr,
        "email_uid": email_uid,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return output_path


def upload_saved_order(order_path: Path):
    try:
        print(order_path)
        # full_path = str(order_path.resolve())
        username, password = extract_credentials_from_filename(order_path)

        if not username or not password:
            return False, f"Could not extract username/password from filename: {order_path}"

        print(f"Uploading order: {order_path}")
        result = upload_order(order_path, username, password)
        print(f"Upload completed: {order_path}")

        if result is None:
            return True, "Upload completed successfully."

        return True, f"Upload completed successfully. Result: {result}"

    except Exception as e:
        print(f"Upload failed for {order_path}: {e}")
        return False, str(e)