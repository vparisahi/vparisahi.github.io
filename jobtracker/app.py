from flask import Flask, render_template, request, redirect, url_for
import requests
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse, parse_qs
import re
import datetime as dt

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
    """Authorize and return a gspread client."""
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_jobs_sheet(gc: gspread.Client):
    """
    Return the jobs_raw worksheet, creating it if needed.
    Ensure there is an 'Applied?' header in column 9.
    """
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

    # Ensure header has at least 9 columns and col 9 is "Applied?"
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
    """
    Return the Applications worksheet, creating it if needed.

    Columns:
      Date Applied | Company | Title | JobID | Source | Job URL | Resume Version | Notes
    """
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
    """
    Load jobs from jobs_raw.

    Expected columns:
      0: Date
      1: Industry
      2: Company
      3: Title
      4: JobID
      5: Location
      6: URL
      7: Source
      8: Applied? (optional)
    """
    gc = get_gspread_client()
    ws = get_jobs_sheet(gc)
    values = ws.get_all_values()

    if len(values) <= 1:
        return []

    rows = values[1:]
    jobs = []

    for row in rows:
        # Skip completely empty rows
        if not any(cell.strip() for cell in row):
            continue

        # Skip accidental header rows
        if len(row) >= 4:
            if (
                row[0].strip().lower() == "date"
                and row[1].strip().lower() == "industry"
                and row[2].strip().lower() == "company"
                and row[3].strip().lower() == "title"
            ):
                continue

        # Ensure at least 9 columns
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


def get_company_board_info(company_name: str):
    """
    Lookup ATS system + Board slug from ATS_SOURCES sheet.

    ATS_SOURCES columns expected:
      Company | Industry | ATS | Board | Active
    """
    gc = get_gspread_client()
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet("ATS_SOURCES")
    except gspread.WorksheetNotFound:
        return None, None

    records = ws.get_all_records()
    target = company_name.strip().lower()

    for r in records:
        active = str(r.get("Active", "")).strip().lower()
        if active not in ("true", "1", "yes", "y"):
            continue

        comp = (r.get("Company", "") or "").strip().lower()
        if comp == target:
            ats = (r.get("ATS", "") or "").strip().lower()
            board = (r.get("Board", "") or "").strip()
            return ats, board

    return None, None


def fetch_greenhouse_jd(company: str, job_url: str) -> str | None:
    """
    Auto-fetch a Greenhouse job description using the board slug from ATS_SOURCES.
    """
    ats, board = get_company_board_info(company)
    if ats != "greenhouse" or not board:
        return None

    parsed = urlparse(job_url)
    query = parse_qs(parsed.query)
    job_id = None

    if "gh_jid" in query:
        job_id = query["gh_jid"][0]
    else:
        # Fallback: last numeric segment in path
        matches = re.findall(r"/(\d+)", parsed.path)
        if matches:
            job_id = matches[-1]

    if not job_id:
        return None

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?content=true"
    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", "")
    except Exception as e:
        print(f"[Tailor] Greenhouse JD fetch failed for {company}: {e}")
        return None


def fetch_lever_jd(company: str, job_url: str) -> str | None:
    """
    Auto-fetch a Lever job description using the board slug from ATS_SOURCES.
    """
    ats, board = get_company_board_info(company)
    if ats != "lever" or not board:
        return None

    parsed = urlparse(job_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    if not path_parts:
        return None

    job_id = path_parts[-1]
    api_url = f"https://api.lever.co/v0/postings/{board}/{job_id}?mode=json"

    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        jd = data.get("descriptionPlain") or data.get("description") or ""
        return jd
    except Exception as e:
        print(f"[Tailor] Lever JD fetch failed for {company}: {e}")
        return None


def mark_job_applied_in_sheet(company: str, job_id: str, source: str):
    """
    Set the 'Applied?' column to 'Yes - YYYY-MM-DD' for the matching job.
    Matching key: (company, job_id, source).
    """
    gc = get_gspread_client()
    ws = get_jobs_sheet(gc)
    values = ws.get_all_values()

    if len(values) <= 1:
        return

    today_str = dt.date.today().isoformat()
    applied_value = f"Yes - {today_str}"

    # values[0] is header, so start from row 2
    for idx, row in enumerate(values[1:], start=2):
        row = row + [""] * (8 - len(row))
        row_company = row[2].strip().lower()
        row_job_id = row[4].strip()
        row_source = row[7].strip().lower()

        if (
            row_company == company.strip().lower()
            and row_job_id == job_id.strip()
            and row_source == source.strip().lower()
        ):
            ws.update_cell(idx, 9, applied_value)
            print(f"Marked applied in jobs_raw: {company} / {job_id} / {source} (row {idx})")
            return


# ------------------------ ROUTES ------------------------


@app.route("/")
def index():
    """
    If index.html exists, render it. Otherwise redirect to /jobs.
    """
    try:
        return render_template("index.html")
    except Exception:
        return redirect(url_for("jobs"))


@app.route("/jobs")
def jobs():
    """Show all jobs from jobs_raw."""
    jobs_list = load_jobs()
    return render_template("jobs.html", jobs=jobs_list)


@app.route("/manual", methods=["GET", "POST"])
def manual_job():
    """
    Add a job manually (LinkedIn, Workday, etc.) without editing the sheet directly.
    On POST, appends a row to jobs_raw and redirects to /jobs.
    """
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

        row = [
            today_str,     # Date
            industry,      # Industry
            company,       # Company
            title,         # Title
            job_id,        # JobID
            location,      # Location
            url,           # URL
            source,        # Source
            "",            # Applied?
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        print(f"Added manual job: {company} / {title} / {source}")

        return redirect(url_for("jobs"))

    return render_template("manual.html")


@app.route("/tailor", methods=["GET", "POST"])
def tailor():
    """
    Tailor resume content for a specific job.

    GET:
      - Tries to auto-fetch JD for Greenhouse / Lever jobs
    POST:
      - Uses JD text (auto or manual) and generates tailored sections
    """
    job_url = request.args.get("job_url") or request.form.get("job_url")
    job_title = request.args.get("title") or request.form.get("title")
    company = request.args.get("company") or request.form.get("company")
    source = request.args.get("source") or request.form.get("source")
    job_id = request.args.get("job_id") or request.form.get("job_id")

    jd_text = ""
    auto_fetched = False
    error = None
    tailored = None

    # Suggested resume version name
    today_str = dt.date.today().isoformat()
    safe_company = (company or "Company").strip().replace(" ", "")
    safe_title = (job_title or "Role").strip().replace(" ", "")
    resume_version = f"Pari_{safe_title}_{safe_company}_{today_str}"

    # Auto-fetch JD on initial GET
    if request.method == "GET" and job_url and company and source:
        src_lower = source.strip().lower()
        if "greenhouse" in src_lower:
            jd = fetch_greenhouse_jd(company, job_url)
            if jd:
                jd_text = jd
                auto_fetched = True
        elif "lever" in src_lower:
            jd = fetch_lever_jd(company, job_url)
            if jd:
                jd_text = jd
                auto_fetched = True

    # On POST, user submitted JD
    if request.method == "POST":
        jd_text = request.form.get("jd_text") or ""
        if not jd_text.strip():
            error = "Please paste or load a job description first."
        else:
            tailored = generate_tailored_sections(job_title or "", company or "", jd_text)

    return render_template(
        "tailor.html",
        job_title=job_title,
        company=company,
        job_url=job_url,
        source=source,
        job_id=job_id,
        jd_text=jd_text,
        auto_fetched=auto_fetched,
        error=error,
        tailored=tailored,
        resume_version=resume_version,
    )


@app.route("/mark_applied", methods=["POST"])
def mark_applied():
    """
    Mark a job as applied in jobs_raw and redirect back to /jobs.
    """
    company = request.form.get("company", "")
    job_id = request.form.get("job_id", "")
    source = request.form.get("source", "")

    if company and job_id and source:
        mark_job_applied_in_sheet(company, job_id, source)

    return redirect(url_for("jobs"))


@app.route("/log_application", methods=["POST"])
def log_application():
    """
    Log a resume version in Applications sheet and mark job as applied.
    """
    company = request.form.get("company", "")
    title = request.form.get("title", "")
    job_id = request.form.get("job_id", "")
    source = request.form.get("source", "")
    job_url = request.form.get("job_url", "")
    resume_version = request.form.get("resume_version", "")
    notes = request.form.get("notes", "")

    gc = get_gspread_client()
    ws = get_applications_sheet(gc)

    today_str = dt.date.today().isoformat()
    row = [
        today_str,
        company,
        title,
        job_id,
        source,
        job_url,
        resume_version,
        notes,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    print(f"Logged application for {company} / {title} / {job_id}")

    if company and job_id and source:
        mark_job_applied_in_sheet(company, job_id, source)

    return redirect(url_for("jobs"))


if __name__ == "__main__":
    app.run(debug=True)

