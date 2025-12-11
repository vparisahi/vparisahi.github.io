import os
import base64
from email.message import EmailMessage
import datetime as dt

import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ------------ Google Sheets (service account) ------------

SHEET_NAME = "JobTracker"
GOOGLE_CREDENTIALS_FILE = "service_account.json"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client() -> gspread.Client:
    credentials = ServiceAccountCredentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE, scopes=SHEETS_SCOPES
    )
    return gspread.authorize(credentials)


def get_applications_last_n_days(n_days: int = 7):
    gc = get_gspread_client()
    sh = gc.open(SHEET_NAME)
    ws = sh.worksheet("Applications")

    records = ws.get_all_records()  # list of dicts
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=n_days)

    recent = []
    for r in records:
        date_str = str(r.get("Date Applied", "")).strip()
        if not date_str:
            continue
        try:
            d = dt.date.fromisoformat(date_str)
        except ValueError:
            # Skip rows with bad date format
            continue

        if d >= cutoff:
            recent.append(r)

    return recent


def format_summary(records):
    if not records:
        return "No applications in the selected period.\n"

    lines = []
    lines.append("Recent Applications:\n")
    for r in records:
        line = (
            f"- {r.get('Date Applied', '')}: "
            f"{r.get('Company', '')} | {r.get('Title', '')} "
            f"(JobID: {r.get('JobID', '')}, Source: {r.get('Source', '')})\n"
            f"  URL: {r.get('Job URL', '')}\n"
            f"  Resume Version: {r.get('Resume Version', '')}\n"
        )
        notes = r.get("Notes", "")
        if notes:
            line += f"  Notes: {notes}\n"
        lines.append(line)
        lines.append("")  # blank line between entries

    return "\n".join(lines)


# ------------ Gmail API (OAuth user) ------------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_CREDENTIALS_FILE = "gmail_credentials.json"  # downloaded from Google Cloud
GMAIL_TOKEN_FILE = "token_gmail.json"             # will be created on first run


def get_gmail_service():
    """
    Authorize the Gmail API using OAuth user credentials.
    On first run, opens a browser window to let you sign in and approve.
    Then stores token_gmail.json for reuse.
    """
    creds = None

    if os.path.exists(GMAIL_TOKEN_FILE):
        creds = UserCredentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


def send_email_via_gmail_api(to_email, subject, body_text):
    """
    Send a plain-text email using the Gmail API.
    'From' will be the account you authorized in the OAuth flow.
    """
    service = get_gmail_service()

    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = "me"
    msg["Subject"] = subject
    msg.set_content(body_text)

    encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    send_body = {"raw": encoded_message}
    sent = service.users().messages().send(userId="me", body=send_body).execute()
    print(f"Gmail API: message sent, ID = {sent.get('id')}")


if __name__ == "__main__":
    # 1) Fetch apps from last 7 days
    apps = get_applications_last_n_days(7)
    summary_text = format_summary(apps)

    # 2) Prepare subject/body
    today = dt.date.today()
    subject = f"Weekly Job Applications Summary (ending {today.isoformat()})"
    body = summary_text

    # 3) Send to yourself (use the same Gmail you authorize in the browser)
    to_email = "pari.sahi2025@gmail.com"  # change if needed

    send_email_via_gmail_api(to_email, subject, body)
    print("Weekly summary email sent via Gmail API.")

