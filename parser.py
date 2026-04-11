import xlrd
import json
import re


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def extract_city_state_zip_from_line(text):
    text = clean_text(text)
    match = re.search(r'^(.*?),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$', text)
    if match:
        city = match.group(1).strip()
        state = match.group(2).strip()
        zip_code = match.group(3).strip()
        return city, state, zip_code
    return "", "", ""


def find_cell_by_text(sheet, target_text):
    target_text = target_text.strip().lower()

    for row_idx in range(sheet.nrows):
        for col_idx in range(sheet.ncols):
            value = clean_text(sheet.cell_value(row_idx, col_idx)).lower()
            if value == target_text:
                return row_idx, col_idx
    return None, None


def to_int_string(value):
    if value is None:
        return ""

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)

    text = clean_text(value)
    if text.endswith(".0"):
        return text[:-2]
    return text


def extract_items(sheet):
    order_details = []

    qty_row, qty_col = find_cell_by_text(sheet, "Qty Ordered")
    part_row, part_col = find_cell_by_text(sheet, "Part Number")

    if qty_row is None or part_row is None or qty_row != part_row:
        return order_details

    header_row = qty_row

    for row_idx in range(header_row + 1, sheet.nrows):
        qty_value = sheet.cell_value(row_idx, qty_col) if qty_col < sheet.ncols else ""
        part_value = sheet.cell_value(row_idx, part_col) if part_col < sheet.ncols else ""

        qty = to_int_string(qty_value)

        sku = clean_text(part_value)
        if sku.endswith(".0"):
            sku = sku[:-2]
        if not qty and not sku:
            continue

        if qty and not sku:
            continue

        if sku.lower().startswith("sub total"):
            continue

        if not re.fullmatch(r'\d+(?:\.\d+)?', qty):
            continue

        order_details.append({
            "quantity": qty,
            "sku": sku
        })

    return order_details


def extract_po_data(file_path, sheet_index=0):
    wb = xlrd.open_workbook(file_path)
    sheet = wb.sheet_by_index(sheet_index)

    result = {
        "order_number": "",
        "customer_name": "",
        "address1": "",
        "city": "",
        "state": "",
        "zip": "",
        "country": "United States",
        "order_lines": []
    }

    po_row, po_col = find_cell_by_text(sheet, "PO Number:")
    if po_row is not None and po_col + 1 < sheet.ncols:
        result["order_number"] = clean_text(sheet.cell_value(po_row, po_col + 1))

    ship_row, ship_col = find_cell_by_text(sheet, "Ship To")
    if ship_row is not None:
        if ship_row + 1 < sheet.nrows:
            result["customer_name"] = clean_text(sheet.cell_value(ship_row + 1, ship_col))

        if ship_row + 3 < sheet.nrows:
            result["address1"] = clean_text(sheet.cell_value(ship_row + 3, ship_col))

        if ship_row + 4 < sheet.nrows:
            city_state_zip_line = clean_text(sheet.cell_value(ship_row + 4, ship_col))
            city, state, zip_code = extract_city_state_zip_from_line(city_state_zip_line)
            result["city"] = city
            result["state"] = state
            result["zip"] = zip_code

    result["order_lines"] = extract_items(sheet)

    return result


if __name__ == "__main__":
    file_path = "153-030326.xls"
    data = extract_po_data(file_path)
    print(json.dumps(data, indent=2))