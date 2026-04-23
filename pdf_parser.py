import re
from typing import Dict, List, Any
import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    full_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text.append(text)

    return "\n".join(full_text)


def parse_city_state_zip(line: str):
    match = re.search(r"(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)", line)
    if match:
        return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
    return "", "", ""


def parse_order_lines(raw_text: str) -> List[Dict[str, Any]]:
    items = []

    pattern = re.compile(
        r"(?m)^(\d+)\s+[A-Z0-9]+\s+([A-Z0-9\-]+)\s+.+?\s+\$[\d,]+\.\d{2}\s+\$[\d,]+\.\d{2}$"
    )

    for match in pattern.finditer(raw_text):
        items.append({
            "quantity": int(match.group(1)),
            "sku": match.group(2).strip()
        })

    return items


def extract_customer_fields(raw_text: str):
    """
    Handles this actual pattern:

    Supplier Ship To
    WILLAND, STEVEN # 247250 LIFFCO POWER EQUIPMENT, INC
    1835 HIGHLAND AVE
    NEW HYDE PARK, NY 11040
    PHONE #: ...

    We only want:
    LIFFCO POWER EQUIPMENT, INC
    1835 HIGHLAND AVE
    NEW HYDE PARK, NY 11040
    """
    customer_name = ""
    address1 = ""
    city = ""
    state = ""
    zip_code = ""

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        if line.upper() == "SUPPLIER SHIP TO":
            if i + 1 < len(lines):
                merged_line = lines[i + 1]

                # Split supplier and customer from same line
                # Example:
                # WILLAND, STEVEN # 247250 LIFFCO POWER EQUIPMENT, INC
                m = re.search(r"#\s*\d+\s+(.+)$", merged_line)
                if m:
                    customer_name = m.group(1).strip()
                else:
                    customer_name = merged_line.strip()

            if i + 2 < len(lines):
                address1 = lines[i + 2]

            if i + 3 < len(lines):
                city, state, zip_code = parse_city_state_zip(lines[i + 3])

            break

    return customer_name, address1, city, state, zip_code


def extract_order_details(pdf_path: str) -> Dict[str, Any]:
    raw_text = extract_text_from_pdf(pdf_path)

    # PO number
    po_match = re.search(r"P\.O\.\s*#:\s*(\d+)", raw_text, re.IGNORECASE)
    po_number = po_match.group(1).strip() if po_match else ""

    customer_name, address1, city, state, zip_code = extract_customer_fields(raw_text)
    items = parse_order_lines(raw_text)

    return {
        "order_number": po_number,
        "customer_name": customer_name,
        "address1": address1,
        "city": city,
        "state": state,
        "zip": zip_code,
        "country": "United States",
        "order_lines": items,
    }


if __name__ == "__main__":
    pdf_path = "PurchaseOrder_2026-03-09.pdf"
    result = extract_order_details(pdf_path)

    from pprint import pprint
    pprint(result)