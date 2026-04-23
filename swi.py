import os
import json
import time
import shutil
from seleniumbase import SB
from urllib.parse import urlparse, parse_qs
import csv

MAPPING_FILE = "orders/order_mapping.csv"

PENDING_DIR = "orders/pending"
PROCESSED_DIR = "orders/processed"
FAILED_DIR = "orders/failed"

INTERVAL_SECONDS = 60
ITEMS_PER_BATCH = 10

os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(FAILED_DIR, exist_ok=True)
os.makedirs(os.path.dirname(MAPPING_FILE), exist_ok=True)


def save_order_mapping(old_order, new_order):
    file_exists = os.path.exists(MAPPING_FILE)

    with open(MAPPING_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["old_order", "new_order"])

        writer.writerow([old_order, new_order])


def chunk_list(data, chunk_size):
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


def extract_credentials_from_filename(file_path):
    """
    Expected filename format:
    username___password___anything.json

    Example:
    600100___Will#2001!___153-030326_20260416_194501.json
    """
    filename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(filename)[0]

    parts = name_without_ext.split("___", 2)
    if len(parts) < 3:
        raise ValueError(
            f"Invalid filename format for credentials: {filename}. "
            f"Expected username___password___rest.json"
        )

    username = parts[0].strip()
    password = parts[1].strip()

    if not username or not password:
        raise ValueError(f"Missing username or password in filename: {filename}")

    return username, password


def login(sb, username, password):
    sb.open("https://www.swiedi.com/willand/b2b.html")

    sb.switch_to_frame('frame[name="Main"]')
    sb.type('input[name="txtUserID"]', username)
    sb.type('input[name="txtPassword"]', password)
    sb.click('input[type="submit"]')
    sb.switch_to_default_content()
    sb.sleep(5)


def add_items_batch(sb, batch):
    """
    Add up to 10 items using Quick Entry page.
    Remove rows with known item errors, then Accept again.
    """
    sb.open("https://www.swiedi.com/willand/webshop.php?mode=quick")
    sb.sleep(3)

    for idx, entry in enumerate(batch, start=1):
        sb.type(f'input[name="item{idx}"]', str(entry["item"]))
        sb.type(f'input[name="qty{idx}"]', str(entry["qty"]))

    sb.click('input[type="submit"][value="Accept"]')
    sb.sleep(3)

    bad_rows = []
    bad_keywords = [
        "discontinued",
        "item already exists",
        "invalid",
        "not found",
    ]

    for idx in range(1, len(batch) + 1):
        try:
            row_selector = f'input[name="item{idx}"]'
            if not sb.is_element_visible(row_selector):
                continue

            row_element = sb.find_element(row_selector)
            tr = row_element.find_element("xpath", "./ancestor::tr")
            tds = tr.find_elements("tag name", "td")

            if not tds:
                continue

            msg = tds[-1].text.strip().lower()
            if any(keyword in msg for keyword in bad_keywords):
                print(f"Row {idx} has issue: {msg}")
                bad_rows.append(idx)

        except Exception as e:
            print(f"Could not inspect row {idx}: {e}")

    if bad_rows:
        for idx in bad_rows:
            try:
                sb.click(f'input[onclick="clear_entry({idx});"]')
                sb.sleep(1)
            except Exception as e:
                print(f"Could not remove row {idx}: {e}")

        sb.click('input[type="submit"][value="Accept"]')
        sb.sleep(3)

    sb.sleep(1)


def checkout_order(sb, order):
    sb.open("https://www.swiedi.com/willand/webshop.php?mode=Checkout")
    sb.sleep(3)

    sb.type('input[name="txtCustPO"]', str(order.get("order_number", "")))
    sb.type('input[name="txtEmail"]', "info@stevenwillandinc.com")

    sb.select_option_by_value('select[name="txtPayment"]', 'On Account')
    sb.click('input#btnAccept')
    sb.sleep(8)

    current_url = sb.driver.current_url
    print("Redirect URL:", current_url)

    parsed = urlparse(current_url)
    params = parse_qs(parsed.query)
    new_order_number = params.get("ordnum", [None])[0]

    if not new_order_number:
        raise Exception("Failed to extract new order number from Swiedi")

    return new_order_number


def upload_order(order_file, username, password):
    with open(order_file, "r", encoding="utf-8") as f:
        order = json.load(f)

    items = [
        {"item": i["sku"], "qty": i["quantity"]}
        for i in order.get("order_lines", [])
        if i.get("sku") and i.get("quantity")
    ]

    if not items:
        raise Exception("No valid items found in order_lines")

    print(f"Using login: {username}")
    print(f"Total items to upload: {len(items)}")

    with SB() as sb:
        login(sb, username, password)

        batches = list(chunk_list(items, ITEMS_PER_BATCH))
        print(f"Total batches: {len(batches)}")

        for batch_index, batch in enumerate(batches, start=1):
            print(f"Adding batch {batch_index}/{len(batches)} with {len(batch)} items")
            add_items_batch(sb, batch)

        new_order_number = checkout_order(sb, order)
        print(f"Swiedi order created: {new_order_number}")

        old_order_number = order.get("order_id") or order.get("order_number")
        save_order_mapping(old_order_number, new_order_number)

        print(f"Mapping saved: {old_order_number} -> {new_order_number}")


def worker_loop():
    print("Swiedi worker started")

    while True:
        files = [
            f for f in os.listdir(PENDING_DIR)
            if f.endswith(".json")
        ]

        for file in files:
            full_path = os.path.join(PENDING_DIR, file)

            try:
                print(f"Processing {file}")

                username, password = extract_credentials_from_filename(full_path)
                upload_order(full_path, username, password)

                shutil.move(
                    full_path,
                    os.path.join(PROCESSED_DIR, file)
                )
                print(f"Uploaded {file}")

            except Exception as e:
                print(f"Failed {file}: {e}")
                shutil.move(
                    full_path,
                    os.path.join(FAILED_DIR, file)
                )

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    worker_loop()