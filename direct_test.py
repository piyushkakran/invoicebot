import os
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from google import genai
import PIL.Image

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Step 1: Image load karo
image = PIL.Image.open("kakran_invoice.jpg")

# Step 2: Gemini se JSON nikalo
response = client.models.generate_content(
    model="gemini-3.1-flash-lite-preview",
    contents=[image, "Is invoice se nikalo JSON mein: invoice_no, date, gst_no, lorry_no, amount, grand_total. Sirf JSON return karo, kuch aur mat likho."]
)

# Step 3: JSON parse karo
raw = response.text.strip().replace("```json", "").replace("```", "").strip()
data = json.loads(raw)
print("Extracted:", data)

# Step 4: Google Sheets mein save karo
creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
)
gc = gspread.authorize(creds)

SHEET_ID = "1da13tTfZY0tgiN5-GL75Hjzug0LhyYkizc4E3IpLa3c"
sh = gc.open_by_key(SHEET_ID)
ws = sh.sheet1

# Headers check karo
if ws.cell(1, 1).value is None:
    ws.append_row(["Invoice No", "Date", "GST No", "Lorry No", "Amount", "Grand Total"])

# Data row add karo
ws.append_row([
    data.get("invoice_no"),
    data.get("date"),
    data.get("gst_no"),
    data.get("lorry_no"),
    data.get("amount"),
    data.get("grand_total")
])

print("Saved to Google Sheets successfully!")