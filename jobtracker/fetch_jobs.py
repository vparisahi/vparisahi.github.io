#!/usr/bin/env python

import datetime as dt
from typing import List, Dict

import requests
import gspread
from google.oauth2.service_account import Credentials

# ----------------- CONFIG -----------------

SHEET_NAME = "JobTracker"
GOOGLE_CREDENTIALS_FILE = "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Max number of NEW jobs to append per run (your daily target)
MAX_NEW_JOBS = 50

# Title keywords to consider it relevant
TITLE_KEYWORDS = [
    "devops",
    "site reliability",
    "sre",
    "platform engineer",
    "platform engineering",
    "platform reliability",
    "cloud engineer",
    "cloud infrastructure",
    "infrastructure engineer",
    "systems engineer",
    "production engineer",
    "reliability engineer",
    "observability",
]

# Stack / responsibilities keywords to prefer strong matches
STACK_KEYWORDS = [
    # CI/CD
    "ci/cd",
    "continuous integration",
    "continuous delivery",
    "deployment pipeline",
    "github actions",
    "gitlab ci",
    "jenkins",
    "azure devops",

    # K8s / containers
    "kubernetes",
    "k8s",
    "eks",
    "gke",
    "aks",
    "docker",
    "helm",
    "service mesh",
    "istio",

    # IaC
    "terraform",
    "pulumi",
    "infrastructure as code",
    "iac",
    "ansible",
    "chef",
    "puppet",

    # Cloud
    "aws",
    "amazon web services",
    "gcp",
    "google cloud",
    "azure",

    # Observability
    "observability",
    "prometheus",
    "grafana",
    "loki",
    "tempo",
    "mimir",
    "datadog",
    "new relic",
    "splunk",
    "elk",
    "elasticsearch",
    "kibana",
    "logstash",
    "opentelemetry",
    "otel",

    # SRE concepts
    "slo",
    "service level objective",
    "error budget",
    "incident response",
    "on-call",
    "on call",
]

# ------------ DEFAULT SOURCES (NO SHEET NEEDED) ------------

DEFAULT_SOURCES: List[Dict] = [
    # SaaS / Cloud
    {"company": "Cloudflare", "industry": "SaaS", "ats": "greenhouse", "board": "cloudflare"},
    {"company": "Datadog", "industry": "SaaS", "ats": "greenhouse", "board": "datadog"},
    {"company": "HashiCorp", "industry": "SaaS", "ats": "greenhouse", "board": "hashicorp"},
    {"company": "Twilio", "industry": "SaaS", "ats": "greenhouse", "board": "twilio"},
    {"company": "Okta", "industry": "Security", "ats": "greenhouse", "board": "okta"},
    {"company": "Airbnb", "industry": "Travel / Tech", "ats": "greenhouse", "board": "airbnb"},
    {"company": "Dropbox", "industry": "SaaS", "ats": "greenhouse", "board": "dropbox"},
    {"company": "Duolingo", "industry": "Education", "ats": "greenhouse", "board": "duolingo"},

    # FinTech
    {"company": "Coinbase", "industry": "FinTech", "ats": "greenhouse", "board": "coinbase"},
    {"company": "Stripe", "industry": "FinTech", "ats": "greenhouse", "board": "stripe"},
    {"company": "Plaid", "industry": "FinTech", "ats": "lever", "board": "plaid"},
    {"company": "Brex", "industry": "FinTech", "ats": "lever", "board": "brex"},

    # Healthcare / Other
    {"company": "Oscar Health", "industry": "Healthcare", "ats": "greenhouse", "board": "oscar"},
    {"company": "Zocdoc", "industry": "Healthcare", "ats": "greenhouse", "board": "zocdoc"},
    {"company": "Instacart", "industry": "Grocery / Delivery", "ats": "greenhouse", "board": "instacart"},
    {"company": "Khan Academy", "industry": "Education", "ats": "greenhouse", "board": "khanacademy"},

    # Example Lever-only SaaS (you can override via sheet later)
    {"company": "Figma", "industry": "SaaS", "ats": "lever", "board": "figma"},
    {"company": "Shopify", "industry": "SaaS / Commerce", "ats": "lever", "board": "shopify"},
]

# -------------------------------------------------------
# Google Sheets helpers
# -------------------------------------------------------

def get_gspread_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_or_create_jobs_sheet(gc: gspread.Client) -> gspread.Worksheet:
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet("jobs_raw")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="jobs_raw", rows=2000, cols=8)
        ws.append_row(
            ["Date", "Industry", "Company", "Title", "JobID", "Location", "URL", "Source"],
            value_input_option="USER_ENTERED",
        )
    return ws


def load_existing_keys(jobs_ws: gspread.Worksheet) -> set:
    values = jobs_ws.get_all_values()
    if len(values) <= 1:
        return set()

    rows = values[1:]  # skip header
    keys = set()
    for row in rows:
        if len(row) < 8:
            row = row + [""] * (8 - len(row))
        _, _, company, _, job_id, _, _, source = row
        key = f"{company.strip().lower()}::{job_id.strip()}::{source.strip().lower()}"
        keys.add(key)
    return keys


# -------------------------------------------------------
# ATS_SOURCES loading (optional override)
# -------------------------------------------------------

def load_ats_sources(gc: gspread.Client) -> List[Dict]:
    """
    Try to load ATS_SOURCES sheet.
    If missing or empty -> return DEFAULT_SOURCES.
    If has at least 1 active row -> use those instead.
    """
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet("ATS_SOURCES")
    except gspread.WorksheetNotFound:
        print("ATS_SOURCES sheet not found; using DEFAULT_SOURCES from code.")
        return DEFAULT_SOURCES

    records = ws.get_all_records()
    sources = []
    for r in records:
        active = str(r.get("Active", "")).strip().lower()
        if active not in ("true", "1", "yes", "y"):
            continue

        company = (r.get("Company", "") or "").strip()
        industry = (r.get("Industry", "") or "").strip()
        ats = (r.get("ATS", "") or "").strip().lower()
        board = (r.get("Board", "") or "").strip()

        if not company or not ats or not board:
            continue

        sources.append(
            {
                "company": company,
                "industry": industry or "",
                "ats": ats,
                "board": board,
            }
        )

    if not sources:
        print("ATS_SOURCES has no active rows; using DEFAULT_SOURCES from code.")
        return DEFAULT_SOURCES

    print(f"Using {len(sources)} ATS sources from ATS_SOURCES sheet.")
    return sources


# -------------------------------------------------------
# Filters
# -------------------------------------------------------

def title_matches(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TITLE_KEYWORDS)


def score_stack_match(text: str) -> int:
    t = text.lower()
    return sum(1 for kw in STACK_KEYWORDS if kw in t)


def is_remote_friendly(location: str, description: str) -> bool:
    loc = (location or "").lower()
    desc = (description or "").lower()

    # Explicit "remote" wins
    if "remote" in loc or "remote" in desc:
        return True

    # Explicit on-site only
    if any(w in loc for w in ["onsite", "on-site", "in-office", "in office"]):
        return False
    if any(w in desc for w in ["onsite", "on-site", "in-office", "in office"]):
        return False

    # Neutral -> accept
    return True


# -------------------------------------------------------
# Greenhouse fetching
# -------------------------------------------------------

def fetch_greenhouse_jobs(company: str, industry: str, board: str) -> List[Dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    print(f"Fetching jobs for {company} (greenhouse, board={board})...")

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Greenhouse] Error fetching board {board}: {e}")
        return []

    jobs = []
    for job in data.get("jobs", []):
        title = job.get("title", "") or ""
        job_id = str(job.get("id", "") or "")
        location = (job.get("location", {}) or {}).get("name", "") or ""
        absolute_url = job.get("absolute_url", "") or ""
        content = job.get("content", "") or ""

        if not title or not job_id or not absolute_url:
            continue

        jobs.append(
            {
                "company": company,
                "industry": industry,
                "title": title,
                "job_id": job_id,
                "location": location,
                "url": absolute_url,
                "source": "Greenhouse",
                "description": content,
            }
        )

    return jobs


# -------------------------------------------------------
# Lever fetching
# -------------------------------------------------------

def fetch_lever_jobs(company: str, industry: str, board: str) -> List[Dict]:
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    print(f"Fetching jobs for {company} (lever, board={board})...")

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Lever] Error fetching board {board}: {e}")
        return []

    jobs = []
    for job in data:
        title = job.get("text", "") or ""
        job_id = job.get("id", "") or ""
        location_obj = job.get("categories", {}) or {}
        location = location_obj.get("location", "") or ""
        hosted_url = job.get("hostedUrl", "") or ""
        description = job.get("descriptionPlain", "") or job.get("description", "") or ""

        if not title or not job_id or not hosted_url:
            continue

        jobs.append(
            {
                "company": company,
                "industry": industry,
                "title": title,
                "job_id": job_id,
                "location": location,
                "url": hosted_url,
                "source": "Lever",
                "description": description,
            }
        )
    return jobs


# -------------------------------------------------------
# Main orchestration
# -------------------------------------------------------

def main():
    gc = get_gspread_client()

    jobs_ws = get_or_create_jobs_sheet(gc)
    existing_keys = load_existing_keys(jobs_ws)
    print(f"Loaded {len(existing_keys)} existing job keys from jobs_raw.")

    ats_sources = load_ats_sources(gc)

    all_candidates: List[Dict] = []

    for src in ats_sources:
        company = src["company"]
        industry = src["industry"]
        ats = src["ats"]
        board = src["board"]

        if ats == "greenhouse":
            jobs = fetch_greenhouse_jobs(company, industry, board)
        elif ats == "lever":
            jobs = fetch_lever_jobs(company, industry, board)
        else:
            print(f"Skipping {company}: ATS {ats!r} not implemented.")
            continue

        if not jobs:
            print(f"  -> 0 raw jobs for {company}")
            continue

        kept_for_company = 0
        for job in jobs:
            title = job["title"]
            desc = job["description"]
            location = job["location"]

            if not title_matches(title):
                continue
            if not is_remote_friendly(location, desc):
                continue

            stack_score = score_stack_match(title + " " + desc)
            if stack_score == 0:
                continue

            all_candidates.append(job)
            kept_for_company += 1

        print(f"  -> {kept_for_company} relevant rows for {company}")

    if not all_candidates:
        print("No relevant jobs found across all ATS sources.")
        return

    today = dt.date.today().isoformat()
    new_rows = []
    added_keys = set()

    for job in all_candidates:
        key = f"{job['company'].strip().lower()}::{job['job_id'].strip()}::{job['source'].strip().lower()}"
        if key in existing_keys or key in added_keys:
            continue

        row = [
            today,
            job["industry"],
            job["company"],
            job["title"],
            job["job_id"],
            job["location"],
            job["url"],
            job["source"],
        ]
        new_rows.append(row)
        added_keys.add(key)

        if len(new_rows) >= MAX_NEW_JOBS:
            break

    if not new_rows:
        print("No new jobs to append (all duplicates or filtered out).")
        return

    print(f"Will append {len(new_rows)} new jobs.")
    jobs_ws.append_rows(new_rows, value_input_option="USER_ENTERED")
    print("Done.")


if __name__ == "__main__":
    main()

