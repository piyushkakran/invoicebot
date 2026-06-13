import os
import json
import time
from dotenv import load_dotenv
from google import genai
import PIL.Image
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

BACKUP_FILE = "failed_saves.json"


class DuplicateInvoiceError(Exception):
    pass


def load_backup():
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            return json.load(f)
    return []


def save_backup(data):
    """Sheet save fail hone pe local backup mein save karo"""
    backup = load_backup()
    backup.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": data
    })
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup, f, indent=2)
    print("⚠️  Sheet save fail hua — data backup mein save ho gaya (failed_saves.json)")


def extract_only(image_path, retries=3):
    """Sirf extract karo — 3 baar retry karega fail hone pe"""

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image nahi mili: {image_path}")

    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY .env mein nahi hai!")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    image = PIL.Image.open(image_path)

    last_error = None

    for attempt in range(1, retries + 1):
        try:
            print(f"  🤖 Gemini se extract kar raha hoon... (attempt {attempt}/{retries})")

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=[image, "Is invoice se nikalo JSON mein sirf yeh fields: invoice_no, date, description, from, to, gst_no, lorry_no, amount, grand_total. Rules: 1) Sirf ek JSON object return karo, koi list nahi. 2) Agar koi field nahi milti to empty string '' rakho, null mat dena. 3) Description mein multiple items hain to comma se join karo ek string mein. 4) Lorry number multiple hain to sirf pehla lo. 5) GST number multiple hain to supplier ka lo. 6) from aur to mein sirf city name. 7) Koi extra text, explanation ya markdown nahi, sirf JSON."]
            )

            raw = response.text.strip().replace("```json", "").replace("```", "").strip()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"  ⚠️  JSON parse fail hua attempt {attempt} pe — raw response: {raw[:100]}")
                last_error = f"JSON parse error: {raw[:100]}"
                time.sleep(2)
                continue

            print(f"  ✅ Extract successful!")
            return data

        except Exception as e:
            last_error = str(e)
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60
                print(f"  ⏳ Rate limit hit — {wait} second wait kar raha hoon...")
                time.sleep(wait)
            elif "quota" in str(e).lower():
                print(f"  ❌ Quota khatam — API plan check karo")
                raise
            else:
                print(f"  ❌ Attempt {attempt} fail: {str(e)}")
                time.sleep(3)

    raise Exception(f"Gemini {retries} attempts ke baad bhi fail raha: {last_error}")


def save_to_sheet(data, sheet_id=None, allow_duplicate=False):
    """Sheet mein save karo — fail hone pe backup mein save karo"""

    if not os.path.exists("/etc/secrets/credentials.json"):
        raise FileNotFoundError("credentials.json nahi mila!")

    try:
        creds = Credentials.from_service_account_file(
            '/etc/secrets/credentials.json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        gc = gspread.authorize(creds)

        SHEET_ID = sheet_id if sheet_id else "1da13tTfZY0tgiN5-GL75Hjzug0LhyYkizc4E3IpLa3c"

        try:
            sh = gc.open_by_key(SHEET_ID)
        except Exception:
            raise Exception(f"Sheet open nahi hui — Sheet ID sahi hai?: {SHEET_ID}")

        ws = sh.sheet1

        # ✅ Duplicate check — invoice_no + date + from + to
        if not allow_duplicate:
            invoice_no = str(data.get("invoice_no") or "").replace(" ", "").replace("/", "").strip().lower()
            date = str(data.get("date") or "").replace(" ", "").replace("/", "").strip().lower()
            from_city = str(data.get("from") or "").replace(" ", "").strip().lower()
            to_city = str(data.get("to") or "").replace(" ", "").strip().lower()

            if invoice_no:
                all_records = ws.get_all_records()
                for row in all_records:
                    row_invoice = str(row.get("Invoice No") or "").replace(" ", "").replace("/", "").strip().lower()
                    row_date = str(row.get("Date") or "").replace(" ", "").replace("/", "").strip().lower()
                    row_from = str(row.get("From") or "").replace(" ", "").strip().lower()
                    row_to = str(row.get("To") or "").replace(" ", "").strip().lower()

                    if (row_invoice == invoice_no and
                        row_date == date and
                        row_from == from_city and
                        row_to == to_city):
                        raise DuplicateInvoiceError(
                            f"Duplicate invoice mila!\n"
                            f"Invoice No : {data.get('invoice_no')}\n"
                            f"Date       : {data.get('date')}\n"
                            f"From       : {data.get('from')}\n"
                            f"To         : {data.get('to')}"
                        )

        if ws.cell(1, 1).value is None:
            ws.append_row(["Invoice No", "Date", "Description", "From", "To", "GST No", "Lorry No", "Amount", "Grand Total"])

        ws.append_row([
            data.get("invoice_no"),
            data.get("date"),
            data.get("description"),
            data.get("from"),
            data.get("to"),
            data.get("gst_no"),
            data.get("lorry_no"),
            data.get("amount"),
            data.get("grand_total")
        ])
        print("  ✅ Google Sheet mein save ho gaya!")

    except DuplicateInvoiceError:
        raise
    except Exception as e:
        save_backup(data)
        raise Exception(f"Sheet save fail DETAIL: {str(e)}")


def extract_and_save(image_path, sheet_id=None):
    """Extract karo aur seedha save karo — WhatsApp flow ke liye"""
    data = extract_only(image_path)
    save_to_sheet(data, sheet_id)
    return data