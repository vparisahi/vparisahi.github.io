"""
seed_sources.py

One-time (or occasional) script to populate the ATS_SOURCES sheet
in your JobTracker Google Sheet.

It will:
- Connect to the JobTracker spreadsheet using service_account.json
- Create ATS_SOURCES if it doesn't exist
- Clear any existing data in ATS_SOURCES
- Write a starter list of ATS sources (companies + ATS + board slug)
"""

import gspread
from google.oauth2.service_account import Credentials

SHEET_NAME = "JobTracker"
GOOGLE_CREDENTIALS_FILE = "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Starter list of companies/boards.
# You can expand this list later if you want more coverage.
STARTER_SOURCES = [
    # Healthcare / HealthTech
    {"Company": "Oscar Health", "Industry": "Healthcare", "ATS": "greenhouse", "Board": "oscar", "Active": "TRUE"},
    {"Company": "Zocdoc", "Industry": "Healthcare", "ATS": "greenhouse", "Board": "zocdoc", "Active": "TRUE"},

    # SaaS / Cloud / Infra
    {"Company": "Cloudflare", "Industry": "SaaS", "ATS": "greenhouse", "Board": "cloudflare", "Active": "TRUE"},
    {"Company": "Datadog", "Industry": "SaaS", "ATS": "greenhouse", "Board": "datadog", "Active": "TRUE"},
    {"Company": "HashiCorp", "Industry": "SaaS", "ATS": "greenhouse", "Board": "hashicorp", "Active": "TRUE"},
    {"Company": "Atlassian", "Industry": "SaaS", "ATS": "greenhouse", "Board": "atlassian", "Active": "TRUE"},
    {"Company": "Okta", "Industry": "Security", "ATS": "greenhouse", "Board": "okta", "Active": "TRUE"},
    {"Company": "Twilio", "Industry": "SaaS", "ATS": "greenhouse", "Board": "twilio", "Active": "TRUE"},

    # Grocery / Delivery / Commerce
    {"Company": "Instacart", "Industry": "Grocery / Delivery", "ATS": "greenhouse", "Board": "instacart", "Active": "TRUE"},

    # FinTech / Payments
    {"Company": "Stripe", "Industry": "FinTech", "ATS": "greenhouse", "Board": "stripe", "Active": "TRUE"},
    {"Company": "Robinhood", "Industry": "FinTech", "ATS": "greenhouse", "Board": "robinhood", "Active": "TRUE"},
    {"Company": "Plaid", "Industry": "FinTech", "ATS": "lever", "Board": "plaid", "Active": "TRUE"},

    # Education / Schools / Universities (examples)
    {"Company": "Khan Academy", "Industry": "Education", "ATS": "greenhouse", "Board": "khanacademy", "Active": "TRUE"},
    {"Company": "Duolingo", "Industry": "Education", "ATS": "greenhouse", "Board": "duolingo", "Active": "TRUE"},

    # Misc tech / infra
    {"Company": "Coinbase", "Industry": "FinTech", "ATS": "greenhouse", "Board": "coinbase", "Active": "TRUE"},
    {"Company": "Dropbox", "Industry": "SaaS", "ATS": "greenhouse", "Board": "dropbox", "Active": "TRUE"},
    {"Company": "Netflix", "Industry": "Media / Tech", "ATS": "greenhouse", "Board": "netflix", "Active": "TRUE"},
    {"Company": "Airbnb", "Industry": "Travel / Tech", "ATS": "greenhouse", "Board": "airbnb", "Active": "TRUE"},
]


def get_gspread_client() -> gspread.Client:
    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def seed_ats_sources():
    gc = get_gspread_client()
    sh = gc.open(SHEET_NAME)

    try:
        ws = sh.worksheet("ATS_SOURCES")
        # Clear existing data
        ws.clear()
    except gspread.WorksheetNotFound:
        # Create sheet if it doesn't exist
        ws = sh.add_worksheet(title="ATS_SOURCES", rows=len(STARTER_SOURCES) + 10, cols=5)

    # Header row
    header = ["Company", "Industry", "ATS", "Board", "Active"]
    ws.append_row(header, value_input_option="USER_ENTERED")

    # Data rows
    rows = []
    for src in STARTER_SOURCES:
        rows.append([
            src["Company"],
            src["Industry"],
            src["ATS"],
            src["Board"],
            src["Active"],
        ])

    ws.append_rows(rows, value_input_option="USER_ENTERED")

    print(f"Seeded ATS_SOURCES with {len(STARTER_SOURCES)} sources.")


if __name__ == "__main__":
    seed_ats_sources()

