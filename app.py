import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

from parser import extract_po_data as extract_excel_order_details
from pdf_parser import extract_order_details as extract_pdf_order_details


app = Flask(__name__)
app.secret_key = "jin120313@Q"

# Simple hardcoded login credentials
USERNAME = "admin"
PASSWORD = "1234"

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

        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")
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
            flash("File uploaded and parsed successfully.", "success")
        except Exception as e:
            flash(f"Error while parsing file: {str(e)}", "danger")
            return redirect(url_for("dashboard"))

    return render_template("dashboard.html", extracted_data=extracted_data)


if __name__ == "__main__":
    app.run(debug=True)