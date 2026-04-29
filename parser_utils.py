import re

def extract_order_number(body):
    """
    Extract PO/order number from email body.

    Supported examples:
      PO 40800
      P.O. 40800
      PO: 40800
      Cust PO 40800
      Purchase Order 40800
    """
    if not body:
        return None

    patterns = [
        r"\bP(?:\.?\s*)O(?:\.?\s*)[:#-]?\s*([A-Za-z0-9\-]+)\b",              # PO 40800 / P.O. 40800 / PO: 40800
        r"\bCust(?:omer)?\s*P(?:\.?\s*)O(?:\.?\s*)[:#-]?\s*([A-Za-z0-9\-]+)\b",
        r"\bPurchase\s+Order\s*[:#-]?\s*([A-Za-z0-9\-]+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, body, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None

def extract_shipping_fields(body):
    """
    Extract Address1, City, State, Zip from email body.

    Supported examples:
      Address1, 1849 Old Country Rd
      City, Riverhead
      State, NY
      Zip, 11901

    Also supports ':' instead of ','.
    """
    result = {
        "address1": None,
        "city": None,
        "state": None,
        "zip": None,
    }

    if not body:
        return result

    patterns = {
        "address1": r"^\s*Address1\s*[:,]\s*(.+?)\s*$",
        "city": r"^\s*City\s*[:,]\s*(.+?)\s*$",
        "state": r"^\s*State\s*[:,]\s*(.+?)\s*$",
        "zip": r"^\s*Zip\s*[:,]\s*(.+?)\s*$",
    }

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        for key, pattern in patterns.items():
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                result[key] = match.group(1).strip()

    return result

def extract_sku_quantity_pairs(body):
    """
    Supports:
    1) Horizontal:
       Sku   Quantity
       511010601 12
       BCZ230TS 6

    2) Vertical:
       Sku
       quantity
       3019-20PS
       1
       3004-20NLP2
       3
    """
    pairs = []
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    lines = [re.sub(r"\s+", " ", line) for line in lines]

    start_index = None

    for i in range(len(lines) - 1):
        if lines[i].lower() == "sku" and lines[i + 1].lower() == "quantity":
            start_index = i + 2
            break

        if re.search(r"\bsku\b", lines[i], re.IGNORECASE) and re.search(r"\bquantity\b", lines[i], re.IGNORECASE):
            start_index = i + 1
            break

    if start_index is None:
        return pairs

    remaining = lines[start_index:]

    if remaining:
        vertical_pairs = []
        i = 0
        while i + 1 < len(remaining):
            sku = remaining[i].strip()
            qty_line = remaining[i + 1].strip()

            if re.fullmatch(r"[A-Z0-9\-]+", sku, re.IGNORECASE) and re.fullmatch(r"\d+", qty_line):
                vertical_pairs.append({
                    "sku": sku.upper(),
                    "quantity": int(qty_line)
                })
                i += 2
            else:
                break

        if vertical_pairs:
            return vertical_pairs

    for line in remaining:
        match = re.match(r"^([A-Z0-9\-]+)\s+(\d+)$", line, re.IGNORECASE)
        if match:
            pairs.append({
                "sku": match.group(1).upper(),
                "quantity": int(match.group(2))
            })

    return pairs