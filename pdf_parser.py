import os
import json
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai
from google.genai import types
import time
import random


load_dotenv()


EXPECTED_KEYS = {
    "order_number": "",
    "customer_name": "",
    "address1": "",
    "city": "",
    "state": "",
    "zip": "",
    "country": "United States",
    "order_lines": [],
}

def run_with_retry(func, max_attempts=3, base_delay=3):
    """
    Retry Gemini API calls when temporary errors happen, especially:
    503 UNAVAILABLE / high demand.
    """

    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()

        except Exception as e:
            last_error = e
            error_text = str(e)

            retryable = (
                "503" in error_text
                or "UNAVAILABLE" in error_text
                or "high demand" in error_text.lower()
                or "temporarily unavailable" in error_text.lower()
                or "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
            )

            if not retryable or attempt == max_attempts:
                raise

            sleep_seconds = base_delay * attempt + random.uniform(0, 2)

            print(
                f"Gemini temporary error. "
                f"Attempt {attempt}/{max_attempts} failed. "
                f"Retrying in {sleep_seconds:.1f}s..."
            )

            time.sleep(sleep_seconds)

    raise last_error

def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_int_string(value: Any) -> str:
    if value is None:
        return ""

    text = clean_text(value)

    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
        return str(number)
    except Exception:
        return text


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Fallback parser in case Gemini wraps JSON in ```json ... ```.
    """
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    return json.loads(text)


def normalize_result(data: Dict[str, Any]) -> Dict[str, Any]:
    result = EXPECTED_KEYS.copy()

    for key in result:
        if key in data:
            result[key] = data[key]

    for key in [
        "order_number",
        "customer_name",
        "address1",
        "city",
        "state",
        "zip",
        "country",
    ]:
        result[key] = clean_text(result.get(key, ""))

    if not result["country"]:
        result["country"] = "United States"

    cleaned_lines: List[Dict[str, str]] = []

    for item in result.get("order_lines", []):
        if not isinstance(item, dict):
            continue

        quantity = to_int_string(item.get("quantity", ""))
        sku = clean_text(item.get("sku", ""))

        if not quantity or not sku:
            continue

        cleaned_lines.append({
            "quantity": quantity,
            "sku": sku
        })

    result["order_lines"] = cleaned_lines

    return result


def extract_order_details(file_path: str, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """
    Extract PO/order details from a PDF using Google Gemini API.

    Returns same JSON format as Excel parser:

    {
      "order_number": "",
      "customer_name": "",
      "address1": "",
      "city": "",
      "state": "",
      "zip": "",
      "country": "United States",
      "order_lines": [
        {
          "quantity": "",
          "sku": ""
        }
      ]
    }
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY in .env file")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    client = genai.Client(api_key=api_key)

    uploaded_file = run_with_retry(
        lambda: client.files.upload(file=file_path),
        max_attempts=3
    )

    prompt = """
    You are an order / purchase order PDF parser.

    Extract the order details from this PDF and return ONLY valid JSON.

    Return exactly this JSON shape:

    {
    "order_number": "",
    "customer_name": "",
    "address1": "",
    "city": "",
    "state": "",
    "zip": "",
    "country": "United States",
    "order_lines": [
        {
        "quantity": "",
        "sku": ""
        }
    ]
    }

    General rules:
    - Return ONLY valid JSON.
    - Do not add explanations.
    - Do not wrap JSON in markdown.
    - Empty fields should be "".
    - country: always "United States" unless another country is explicitly shown.

    Order number rules:
    - order_number: purchase order number / PO number / order number.
    - For labels like "PO # : 12128-00 ()", return only "12128-00".
    - Remove empty parentheses, extra spaces, and punctuation around the PO number.

    Customer/address rules:
    - Prefer the "Ship To" block when it exists.
    - If there is no "Ship To" block, use the customer/company address block at the top-left or top of the PDF.
    - The customer/company address block is often the first block before fields like "Pay To", "Vendor", "PO #", "PO Type", "Date Created", or item tables.
    - customer_name should be the first company/name line in that address block.
    - address1 should be the first street address line in that address block.
    - city, state, zip should be parsed from the city/state/zip line in that address block.
    - Always return the state as its official USPS two-letter abbreviation.
    - If the PDF contains the full state name, convert it to the USPS abbreviation.
    - Examples:
    - New Jersey → NJ
    - New York → NY
    - California → CA
    - Pennsylvania → PA
    - Connecticut → CT
    - Massachusetts → MA
    - Virginia → VA
    - North Carolina → NC
    - South Carolina → SC
    - Florida → FL
    - Texas → TX
    - If the PDF already contains a two-letter state abbreviation, preserve it exactly.
    - Never return the full state name.
    - Do not use the vendor/pay-to name as customer_name.
    - Do not use "Redmax", "RedMax", "Steven Willand", or other vendor/pay-to names as customer_name unless they are clearly inside the Ship To block.
    - Ignore phone numbers, fax numbers, emails, account numbers, PO status, dates, totals, and payment info when extracting address.
    - If both vendor and customer blocks exist, use Ship To/customer delivery address, not Pay To/vendor address.

    Order line rules:
    - Extract each ordered item from the item table.
    - quantity: item quantity as string, no decimals if whole number. Example: "1", not "1.00".
    - If no explicit quantity column is shown, but each item appears as a separate ordered line, use "1".

    SKU extraction rules:
    - sku must be the actual model / part number only.
    - sku must NOT include brand names, manufacturer names, vendor prefixes, or descriptive words.
    - Remove prefixes such as:
    - "RedMax"
    - "RedMax/"
    - "SWI"
    - "SWI."
    - "RedMax/SWI"
    - "RedMax/SWI."
    - "Little Wonder"
    - "Little Wonder/"
    - If the Model column contains a value like:
    "Little Wonder/5511-02-01"
    return only:
    "5511-02-01"
    - If the Model column contains a value like:
    "RedMax/SWI.EBZ5150-RH"
    return only:
    "EBZ5150-RH"
    - If the item text contains a value like:
    "RedMax/ EBZ8560"
    return only:
    "EBZ8560"
    - If the item text contains a value like:
    "RedMax/ BCZ265TS"
    return only:
    "BCZ265TS"

    Model-column priority:
    - For purchase order tables with columns like:
    "Order Ref No | Model | Description | Total Cost"
    use the value under the Model column as the sku.
    - If the Model value contains a brand prefix and a slash, extract only the part after the slash.
    - If the Model value contains a brand/vendor prefix and a dot, extract only the part after the dot.
    - Do not use the Description column as sku unless the Model column is empty.
    - Do not include customer reference words like "Devine GC", "Ichabod Crane", "Syracuse Parks", or other job/customer names in sku.

    Non-item exclusions:
    - Do not include freight, hose kits, accessories, subtotal, tax, total, comments, payment info, or service-only charge lines as order items unless they are clearly requested as ordered products.
    - Do not include rows that only contain cost/total values.
    """
    response = run_with_retry(
        lambda: client.models.generate_content(
            model=model,
            contents=[prompt, uploaded_file],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "order_number": {"type": "string"},
                        "customer_name": {"type": "string"},
                        "address1": {"type": "string"},
                        "city": {"type": "string"},
                        "state": {"type": "string"},
                        "zip": {"type": "string"},
                        "country": {"type": "string"},
                        "order_lines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "quantity": {"type": "string"},
                                    "sku": {"type": "string"}
                                },
                                "required": ["quantity", "sku"]
                            }
                        }
                    },
                    "required": [
                        "order_number",
                        "customer_name",
                        "address1",
                        "city",
                        "state",
                        "zip",
                        "country",
                        "order_lines"
                    ]
                }
            )
        ),
        max_attempts=7
    )
    raw_text = response.text or ""

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = extract_json_from_text(raw_text)

    return normalize_result(data)


if __name__ == "__main__":
    import os
    import json

    uploads_dir = "uploads"
    output_dir = "uploads"

    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(uploads_dir):
        if not filename.lower().endswith(".pdf"):
            continue

        file_path = os.path.join(uploads_dir, filename)
        base_name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_dir, f"{base_name}.json")

        print(f"Processing: {file_path}")

        try:
            data = extract_order_details(file_path)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            print(f"Saved: {output_path}")

        except Exception as e:
            print(f"Failed: {file_path}")
            print(f"Error: {e}")