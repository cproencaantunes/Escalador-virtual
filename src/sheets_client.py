"""Google Sheets via service account."""
import os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _service():
    sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if not sa:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT não definida")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def escrever_batch(spreadsheet_id: str, updates: list):
    if not updates:
        return
    svc = _service()
    for i in range(0, len(updates), 1000):
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates[i:i+1000]}
        ).execute()

def col_letra(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s
