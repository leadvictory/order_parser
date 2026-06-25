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

def extract_terms(body: str):
    match = re.search(
        r"(?im)^\s*(?:Terms|Payment\s+Terms)\s*:\s*(.+?)\s*$",
        body or ""
    )

    return match.group(1).strip() if match else ""


def extract_freight(body: str):
    """
    Extract:
    Freight: FREE
    """
    match = re.search(
        r"(?im)^\s*Freight\s*:\s*(.+?)\s*$",
        body or ""
    )

    if match:
        return match.group(1).strip()

    return ""

def extract_type(body: str):
    """
    Extract:
    Type: On Account
    """
    match = re.search(
        r"(?im)^\s*Type\s*:\s*(.+?)\s*$",
        body or ""
    )

    if match:
        return match.group(1).strip()

    return ""


def extract_ship_to(body: str):
    match = re.search(
        r"(?im)^\s*(?:ShipTo|Shipto\s+Id)\s*:?\s*(.+?)\s*$",
        body or ""
    )

    return match.group(1).strip() if match else ""


def extract_ship_via(body: str):
    match = re.search(
        r"(?im)^\s*ShipVia\s*:?\s*(.+?)\s*$",
        body or ""
    )

    if match:
        return match.group(1).strip()

    match = re.search(
        r"(?im)^\s*Shipvia\s+(.+?)\s*$",
        body or ""
    )

    return match.group(1).strip() if match else ""

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
       Quantity
       3019-20PS
       1
       3004-20NLP2
       3

    3) Horizontal with QTY:
       SKU   QTY
       GCWR2 2

    4) EA format:
       72 ea. EBZ8560
       2 ea. GCWR2 – Grass Catchers
    """
    pairs = []
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    lines = [re.sub(r"\s+", " ", line) for line in lines]

    start_index = None

    # Find SKU / Quantity or SKU / QTY header
    for i in range(len(lines) - 1):
        current = lines[i].lower()
        next_line = lines[i + 1].lower()

        if current == "sku" and next_line in {"quantity", "qty"}:
            start_index = i + 2
            break

        if (
            re.search(r"\bsku\b", lines[i], re.IGNORECASE)
            and re.search(r"\b(quantity|qty)\b", lines[i], re.IGNORECASE)
        ):
            start_index = i + 1
            break

    # Case 1/2/3: SKU Quantity / SKU QTY table
    if start_index is not None:
        remaining = lines[start_index:]

        # Vertical format
        vertical_pairs = []
        i = 0

        while i + 1 < len(remaining):
            sku = remaining[i].strip()
            qty_line = remaining[i + 1].strip()

            if (
                re.fullmatch(r"[A-Z0-9\-]+", sku, re.IGNORECASE)
                and re.fullmatch(r"\d+", qty_line)
            ):
                vertical_pairs.append({
                    "sku": sku.upper(),
                    "quantity": int(qty_line)
                })
                i += 2
            else:
                break

        if vertical_pairs:
            return vertical_pairs

        # Horizontal format
        for line in remaining:
            match = re.match(r"^([A-Z0-9\-]+)\s+(\d+)$", line, re.IGNORECASE)
            if match:
                pairs.append({
                    "sku": match.group(1).upper(),
                    "quantity": int(match.group(2))
                })

        if pairs:
            return pairs

    # Case 4: "72 ea. EBZ8560" or "2 ea. GCWR2 – Grass Catchers"
    ea_pairs = []

    for line in lines:
        match = re.match(
            r"^\s*(\d+)\s+ea\.?\s+([A-Z0-9\-]+)",
            line,
            re.IGNORECASE
        )

        if match:
            quantity = int(match.group(1))
            sku = match.group(2).strip().upper()

            ea_pairs.append({
                "sku": sku,
                "quantity": quantity
            })

    if ea_pairs:
        return ea_pairs

    return []