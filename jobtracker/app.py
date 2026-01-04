from flask import Flask, render_template, request, redirect, url_for
import requests
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse, parse_qs
import re
import datetime as dt

import fetch_jobs
from utils.tailoring import generate_tailored_sections

app = Flask(__name__)

# ---------------- Google Sheets config ----------------

SHEET_NAME = "JobTracker"
GOOGLE_CREDENTIALS_FILE = "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_jobs_sheet(gc: gspread.Client):
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet("jobs_raw")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="jobs_raw", rows=2000, cols=9)
        ws.append_row(
            ["Date", "Industry", "Company", "Title", "JobID", "Location", "URL", "Source", "Applied?"],
            value_input_option="USER_ENTERED",
        )
        return ws

    header = ws.row_values(1)
    if len(header) < 9:
        header = header + [""] * (9 - len(header))
        header[8] = "Applied?"
        ws.update("A1:I1", [header])
    elif header[8].strip() == "":
        header[8] = "Applied?"
        ws.update("A1:I1", [header])

    return ws


def get_applications_sheet(gc: gspread.Client):
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet("Applications")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Applications", rows=2000, cols=8)
        ws.append_row(
            [
                "Date Applied",
                "Company",
                "Title",
                "JobID",
                "Source",
                "Job URL",
                "Resume Version",
                "Notes",
            ],
            value_input_option="USER_ENTERED",
        )
    return ws


def load_jobs():
    gc = get_gspread_client()
    ws = get_jobs_sheet(gc)
    values = ws.get_all_values()

    if len(values) <= 1:
        return []

    rows = values[1:]
    jobs = []

    for row in rows:
        if not any(cell.strip() for cell in row):
            continue

        if len(row) >= 4:
            if (
                row[0].strip().lower() == "date"
                and row[1].strip().lower() == "industry"
                and row[2].strip().lower() == "company"
                and row[3].strip().lower() == "title"
            ):
                continue

        row = row + [""] * (9 - len(row))

        jobs.append(
            {
                "date_found": row[0] or "",
                "industry": row[1] or "",
                "company": row[2] or "",
                "title": row[3] or "",
                "job_id": str(row[4] or ""),
                "location": row[5] or "",
                "url": row[6] or "",
                "source": row[7] or "",
                "applied": row[8] or "",
            }
        )

    return jobs


# ------------------------ ROUTES ------------------------

@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception:
        return redirect(url_for("jobs"))


@app.route("/jobs")
def jobs():
    jobs_list = load_jobs()
    return render_template("jobs.html", jobs=jobs_list)


@app.route("/refresh_jobs", methods=["POST"])
def refresh_jobs():
    """
    Manual trigger for job ingestion.
    """
    try:
        fetch_jobs.main()
        return redirect(url_for("jobs"))
    except Exception as e:
        return f"Refresh failed: {e}", 500


@app.route("/manual", methods=["GET", "POST"])
def manual_job():
    if request.method == "POST":
        company = request.form.get("company", "").strip()
        title = request.form.get("title", "").strip()
        industry = request.form.get("industry", "").strip()
        job_id = request.form.get("job_id", "").strip()
        location = request.form.get("location", "").strip()
        url = request.form.get("url", "").strip()
        source = request.form.get("source", "").strip() or "Manual"

        today_str = dt.date.today().isoformat()

        gc = get_gspread_client()
        ws = get_jobs_sheet(gc)

        ws.append_row(
            [
                today_str,
                industry,
                company,
                title,
                job_id,
                location,
                url,
                source,
                "",
            ],
            value_input_option="USER_ENTERED",
        )

        return redirect(url_for("jobs"))

    return render_template("manual.html")


@app.route("/mark_applied", methods=["POST"])
def mark_applied():
    company = request.form.get("company", "")
    job_id = request.form.get("job_id", "")
    source = request.form.get("source", "")

    if company and job_id and source:
        gc = get_gspread_client()
        ws = get_jobs_sheet(gc)
        values = ws.get_all_values()
        today_str = dt.date.today().isoformat()

        for idx, row in enumerate(values[1:], start=2):
            row = row + [""] * (9 - len(row))
            if (
                row[2].strip().lower() == company.lower()
                and row[4].strip() == job_id
                and row[7].strip().lower() == source.lower()
            ):
                ws.update_cell(idx, 9, f"Yes - {today_str}")
                break

    return redirect(url_for("jobs"))


if __name__ == "__main__":
    app.run(debug=True)
