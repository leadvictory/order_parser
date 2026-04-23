import os
import csv
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

from parser import extract_po_data as extract_excel_order_details
from pdf_parser import extract_order_details as extract_pdf_order_details

import os
import csv
import re
import json
from datetime import datetime
from functools import wraps

from swi import upload_order

PENDING_FOLDER = os.path.join("orders", "pending")
os.makedirs(PENDING_FOLDER, exist_ok=True)

def clean_filename_part(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', value)
    return value[:100]


def save_extracted_data_to_pending(original_filename: str, extracted_data, username: str, password: str):
    base_name = os.path.splitext(os.path.basename(original_filename))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_filename = f"{username}___{password}___{base_name}_{timestamp}.json"
    output_path = os.path.join(PENDING_FOLDER, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(extracted_data, f, indent=4, ensure_ascii=False)

    return output_path

app = Flask(__name__)
app.secret_key = "jin120313@Q"

# File that stores login users
USERS_CSV = "Users.csv"

# Upload settings
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_uploaded_file(file_path: str, ext: str):
    """
    Route the uploaded file to the correct parser.
    """
    ext = ext.lower()

    if ext == "pdf":
        return extract_pdf_order_details(file_path)

    if ext in {"xlsx", "xls"}:
        return extract_excel_order_details(file_path)

    raise ValueError("Unsupported file type")


def validate_user(username: str, password: str, csv_path: str = USERS_CSV) -> bool:
    """
    Validate login using users.csv
    Required headers:
    - Login ID
    - Password
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Users file not found: {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("users.csv is empty or missing headers")

        # Keep original header names exactly as in CSV
        required_headers = {"id_webuser", "passwd_webuser"}
        actual_headers = set(reader.fieldnames)

        missing = required_headers - actual_headers
        if missing:
            raise ValueError(f"Missing required columns in users.csv: {', '.join(missing)}")

        for row in reader:
            login_id = (row.get("id_webuser") or "").strip()
            user_password = (row.get("passwd_webuser") or "").strip()

            if login_id == username and user_password == password:
                return True

    return False

@app.route("/", methods=["GET"])
def home():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        try:
            if validate_user(username, password):
                session["logged_in"] = True
                session["username"] = username
                session["password"] = password
                flash("Login successful.", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "danger")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Login error: {str(e)}", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    extracted_data = None

    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if not uploaded_file or uploaded_file.filename == "":
            flash("Please choose a file.", "danger")
            return redirect(url_for("dashboard"))

        if not allowed_file(uploaded_file.filename):
            flash("Only PDF, XLSX, and XLS files are allowed.", "danger")
            return redirect(url_for("dashboard"))

        filename = secure_filename(uploaded_file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        uploaded_file.save(file_path)

        try:
            ext = filename.rsplit(".", 1)[1].lower()
            extracted_data = parse_uploaded_file(file_path, ext)

            saved_path = save_extracted_data_to_pending(
                filename,
                extracted_data,
                session.get("username", ""),
                session.get("password", "")
            )

            flash("File uploaded and parsed successfully.", "success")
            flash(f"Saved to pending: {saved_path}", "success")
        except Exception as e:
            flash(f"Error while parsing file: {str(e)}", "danger")
            return redirect(url_for("dashboard"))

    return render_template(
        "dashboard.html",
        extracted_data=extracted_data,
        username=session.get("username")
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=80)