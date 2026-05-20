import os
import json
import re
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai
from google.genai import types


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

    uploaded_file = client.files.upload(file=file_path)

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
    - Do not use the vendor/pay-to name as customer_name.
    - Do not use "Redmax", "RedMax", "Steven Willand", or other vendor/pay-to names as customer_name unless they are clearly inside the Ship To block.
    - Ignore phone numbers, fax numbers, emails, account numbers, PO status, dates, totals, and payment info when extracting address.
    - If both vendor and customer blocks exist, use Ship To/customer delivery address, not Pay To/vendor address.

    Order line rules:
    - Extract each ordered item from the item table.
    - quantity: item quantity as string, no decimals if whole number. Example: "8", not "8.00".
    - sku: extract only the clean model / part number.
    - For tables with columns like "Model (VndCode) Description Order Recv Cost Ext Cost", use the Model value as sku and the Order quantity as quantity.
    - If a row contains both Model and VndCode, prefer the Model value as sku unless Product ID is clearly the required SKU.
    - sku must NOT include brand/vendor prefixes such as "RedMax", "SWI", "RedMax/SWI", "RedMax/", "SWI.", or "RedMax/SWI.".
    - Do not include customer reference words like "Devine GC", "Ichabod Crane", or other customer/job names in sku.
    - Do not include freight, shipping charge, discount, subtotal, tax, total, amount paid, current balance, comments, or service-only charge lines as order items.
    """
    response = client.models.generate_content(
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