import dataclasses
import datetime as dt
import logging
import os
from typing import Iterable, List, Dict, Any, Optional, Tuple

import requests
import gspread
from google.oauth2.service_account import Credentials

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------

LOG_LEVEL = os.getenv("JOBTRACKER_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Google Sheets config
# -------------------------------------------------------------------

SHEET_NAME = "JobTracker"
GOOGLE_CREDENTIALS_FILE = "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# -------------------------------------------------------------------
# Domain model
# -------------------------------------------------------------------

@dataclasses.dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    remote: bool
    posted_at: Optional[str] = None
    raw: Dict[str, Any] = dataclasses.field(default_factory=dict)


TARGET_KEYWORDS = [
    "devops",
    "site reliability",
    "sre",
    "cloud engineer",
    "platform engineer",
    "infrastructure",
]

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _matches_keywords(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in TARGET_KEYWORDS)


def _looks_remote(location: str) -> bool:
    loc = (location or "").lower()
    return any(word in loc for word in ["remote", "anywhere", "distributed"])


def get_gspread_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


# -------------------------------------------------------------------
# Sheets access
# -------------------------------------------------------------------

def get_ats_sources(gc: gspread.Client) -> List[Dict[str, str]]:
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet("ATS_SOURCES")
    records = ws.get_all_records()

    active = []
    for r in records:
        if str(r.get("Active", "")).strip().lower() in ("true", "1", "yes", "y"):
            active.append(r)

    return active


def get_existing_job_keys(gc: gspread.Client) -> set[Tuple[str, str, str]]:
    """
    Return set of (company, job_id, source) already in jobs_raw
    """
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet("jobs_raw")
    values = ws.get_all_values()

    keys = set()
    for row in values[1:]:
        row = row + [""] * (9 - len(row))
        company = row[2].strip().lower()
        job_id = row[4].strip()
        source = row[7].strip().lower()
        if company and job_id and source:
            keys.add((company, job_id, source))
    return keys


def append_jobs(gc: gspread.Client, rows: List[List[str]]) -> None:
    if not rows:
        return
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet("jobs_raw")
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# -------------------------------------------------------------------
# Fetchers
# -------------------------------------------------------------------

def fetch_greenhouse(board: str, company: str) -> Iterable[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("jobs", []):
        title = item.get("title", "")
        location = item.get("location", {}).get("name", "") or ""
        job_url = item.get("absolute_url", "")
        job_id = str(item.get("id", ""))

        if not _matches_keywords(title):
            continue

        yield Job(
            source="greenhouse",
            company=company,
            title=title,
            location=location,
            url=job_url,
            remote=_looks_remote(location),
            posted_at=item.get("updated_at"),
            raw={"job_id": job_id},
        )


def fetch_lever(board: str, company: str) -> Iterable[Job]:
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for item in data:
        title = item.get("text", "")
        location = item.get("categories", {}).get("location", "")
        job_url = item.get("hostedUrl") or item.get("applyUrl", "")
        job_id = item.get("id", "")

        if not _matches_keywords(title):
            continue

        yield Job(
            source="lever",
            company=company,
            title=title,
            location=location,
            url=job_url,
            remote=_looks_remote(location),
            posted_at=str(item.get("createdAt")),
            raw={"job_id": job_id},
        )


# -------------------------------------------------------------------
# Main ingestion
# -------------------------------------------------------------------

def main() -> None:
    logger.info("Starting job ingestion")

    gc = get_gspread_client()
    ats_sources = get_ats_sources(gc)
    existing_keys = get_existing_job_keys(gc)

    today = dt.date.today().isoformat()
    new_rows: List[List[str]] = []

    for src in ats_sources:
        company = src["Company"]
        industry = src.get("Industry", "")
        ats = src["ATS"].lower()
        board = src["Board"]

        logger.info("Fetching %s jobs for %s", ats, company)

        try:
            if ats == "greenhouse":
                jobs = fetch_greenhouse(board, company)
            elif ats == "lever":
                jobs = fetch_lever(board, company)
            else:
                logger.warning("Unsupported ATS %s for %s", ats, company)
                continue

            for job in jobs:
                if not job.remote:
                    continue

                job_id = job.raw.get("job_id", "")
                key = (company.lower(), job_id, job.source)

                if key in existing_keys:
                    continue

                row = [
                    today,            # Date
                    industry,         # Industry
                    company,          # Company
                    job.title,        # Title
                    job_id,           # JobID
                    job.location,     # Location
                    job.url,          # URL
                    job.source,       # Source
                    "",               # Applied?
                ]
                new_rows.append(row)
                existing_keys.add(key)

        except Exception as exc:
            logger.exception("Failed fetching jobs for %s: %s", company, exc)

    append_jobs(gc, new_rows)

    logger.info("Job ingestion complete. Added %d new jobs.", len(new_rows))


if __name__ == "__main__":
    main()
