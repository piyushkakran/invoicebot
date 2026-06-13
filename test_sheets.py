import gspread
from google.oauth2.service_account import Credentials

creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)

gc = gspread.authorize(creds)

SHEET_ID = "1da13tTfZY0tgiN5-GL75Hjzug0LhyYkizc4E3IpLa3c"
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

ws.append_row(["INV-001", "2026-04-17", "GST123", "HR-01", "1000", "1180"])
print("Success! Check your Google Sheet.")