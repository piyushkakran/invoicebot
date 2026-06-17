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


def save_backup(data, sheet_id=None, client_fields=None):
    """Sheet save fail hone pe local backup mein save karo"""
    backup = load_backup()
    backup.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
        "sheet_id": sheet_id,
        "client_fields": client_fields
    })
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup, f, indent=2)
    print("⚠️  Sheet save fail hua — data backup mein save ho gaya (failed_saves.json)")


def find_duplicate_check_fields(client_fields):
    """Find relevant fields for duplicate detection"""
    if not client_fields:
        return None, None, None, None

    invoice_field = None
    date_field = None
    from_field = None
    to_field = None

    for field in client_fields:
        f_lower = field.lower()
        if "invoice" in f_lower:
            invoice_field = field
        elif "date" in f_lower and not date_field:
            date_field = field
        elif "from" in f_lower and not from_field:
            from_field = field
        elif "to" in f_lower and not to_field:
            to_field = field
    return invoice_field, date_field, from_field, to_field


def build_extraction_prompt(client_fields):
    """Dynamic prompt with conditional rules"""
    if not client_fields:
        client_fields = ["Invoice No", "Date", "Description", "From", "To", "GST No", "Lorry No", "Amount", "Grand Total"]

    keys = [f.lower().replace(" ", "_") for f in client_fields]
    keys_str = ", ".join(keys)

    prompt = (
        f"Is invoice se nikalo JSON mein sirf yeh fields: {keys_str}. "
        f"Rules: 1) Sirf ek JSON object return karo, koi list nahi. "
        f"2) Har field ki value single string honi chahiye (empty string '' agar nahi mila)."
    )

    field_names = " ".join([f.lower() for f in client_fields])
    if "description" in field_names:
        prompt += " 3) Description multiple items ho to comma se join karke ek string banao."
    if "lorry" in field_names:
        prompt += " 4) Lorry number multiple hain to sirf pehla lo."
    if "gst" in field_names:
        prompt += " 5) GST number multiple hain to supplier ka lo."
    if "from" in field_names or "to" in field_names:
        prompt += " 6) From aur To mein sirf city name."

    prompt += " 7) Koi extra text, explanation ya markdown nahi, sirf JSON."
    return prompt


def detect_schema_from_photo(image_path, retries=2):
    """Photo se column headers detect karta hai"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image nahi mili: {image_path}")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    image = PIL.Image.open(image_path)

    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=[image,
                    "Yeh ek invoice register ya Excel sheet ka photo hai. "
                    "Iske column headers (field names) ko detect karke JSON array of strings mein return karo. "
                    "Sirf headers ka naam, kuch aur mat likho. "
                    "Example output: [\"Invoice No\", \"Date\", \"Lorry No\", \"Amount\", \"From\", \"To\"]"]
            )

            raw = response.text.strip().replace("```json", "").replace("```", "").strip()

            try:
                fields = json.loads(raw)
                if isinstance(fields, list):
                    fields = [str(f).strip() for f in fields if str(f).strip()]
                    print(f"  ✅ Schema detected: {fields}")
                    return fields
            except:
                pass

            # Fallback: try to extract array manually
            if "[" in raw and "]" in raw:
                try:
                    start = raw.find("[")
                    end = raw.rfind("]") + 1
                    fields = json.loads(raw[start:end])
                    fields = [str(f).strip() for f in fields if str(f).strip()]
                    return fields
                except:
                    pass

        except Exception as e:
            print(f"Schema detection attempt {attempt} failed: {e}")
            time.sleep(2)

    print("⚠️ Could not detect schema from photo")
    return None


def extract_only(image_path, client_fields=None, retries=3):
    """Dynamic extraction"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image nahi mili: {image_path}")

    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY .env mein nahi hai!")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    image = PIL.Image.open(image_path)

    prompt = build_extraction_prompt(client_fields)
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            print(f"  🤖 Gemini se extract kar raha hoon... (attempt {attempt}/{retries})")

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=[image, prompt]
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


def save_to_sheet(data, sheet_id=None, allow_duplicate=False, client_fields=None):
    """Sheet mein save karo — improved duplicate check with from/to"""
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

        if not client_fields:
            client_fields = ["Invoice No", "Date", "Description", "From", "To", "GST No", "Lorry No", "Amount", "Grand Total"]

        # ✅ Improved Duplicate check (Invoice + Date + From + To)
        if not allow_duplicate:
            inv_field, date_field, from_field, to_field = find_duplicate_check_fields(client_fields)
            if inv_field:
                inv_key = inv_field.lower().replace(" ", "_")
                invoice_no = str(data.get(inv_key) or "").replace(" ", "").replace("/", "").strip().lower()

                if invoice_no:
                    all_records = ws.get_all_records()
                    for row in all_records:
                        row_invoice = str(row.get(inv_field) or "").replace(" ", "").replace("/", "").strip().lower()
                        match = (row_invoice == invoice_no)

                        if date_field:
                            date_key = date_field.lower().replace(" ", "_")
                            row_date = str(row.get(date_field) or "").replace(" ", "").replace("/", "").strip().lower()
                            data_date = str(data.get(date_key) or "").replace(" ", "").replace("/", "").strip().lower()
                            match = match and (row_date == data_date)

                        if from_field:
                            from_key = from_field.lower().replace(" ", "_")
                            row_from = str(row.get(from_field) or "").replace(" ", "").strip().lower()
                            data_from = str(data.get(from_key) or "").replace(" ", "").strip().lower()
                            match = match and (row_from == data_from)

                        if to_field:
                            to_key = to_field.lower().replace(" ", "_")
                            row_to = str(row.get(to_field) or "").replace(" ", "").strip().lower()
                            data_to = str(data.get(to_key) or "").replace(" ", "").strip().lower()
                            match = match and (row_to == data_to)

                        if match:
                            raise DuplicateInvoiceError(
                                f"Duplicate invoice mila!\n"
                                f"Invoice No : {data.get(inv_key)}\n"
                                f"Date       : {data.get(date_key) if date_field else 'N/A'}\n"
                                f"From       : {data.get(from_key) if from_field else 'N/A'}\n"
                                f"To         : {data.get(to_key) if to_field else 'N/A'}"
                            )
            else:
                print("⚠️ No 'invoice' field found in schema — skipping duplicate check")

        # Write headers if sheet is empty
        if ws.cell(1, 1).value is None:
            ws.append_row(client_fields)

        # Build dynamic row
        row = []
        for field in client_fields:
            key = field.lower().replace(" ", "_")
            row.append(data.get(key, ""))

        ws.append_row(row)
        print("  ✅ Google Sheet mein save ho gaya!")

    except DuplicateInvoiceError:
        raise
    except Exception as e:
        save_backup(data, sheet_id, client_fields)
        raise Exception(f"Sheet save fail DETAIL: {str(e)}")


def extract_and_save(image_path, sheet_id=None, client_fields=None):
    """Extract karo aur seedha save karo"""
    data = extract_only(image_path, client_fields)
    save_to_sheet(data, sheet_id, client_fields=client_fields)
    return data