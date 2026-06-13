import json
import os
import time
from gemini_test import save_to_sheet

BACKUP_FILE = "failed_saves.json"

FIELDS = [
    ("invoice_no", "Invoice No"),
    ("date", "Date"),
    ("description", "Description"),
    ("from", "From"),
    ("to", "To"),
    ("gst_no", "GST No"),
    ("lorry_no", "Lorry No"),
    ("amount", "Amount"),
    ("grand_total", "Grand Total")
]


def get_log_file(sheet_id):
    return f"processed_log_{sheet_id[:8]}.json"


def load_backup():
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r") as f:
            return json.load(f)
    return []


def save_backup(data):
    with open(BACKUP_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_log(sheet_id):
    log_file = get_log_file(sheet_id)
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            return json.load(f)
    return {}


def save_log(log, sheet_id):
    log_file = get_log_file(sheet_id)
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)


def fill_missing_fields(data):
    """Missing fields user se maango"""
    filled_fields = {}

    for key, label in FIELDS:
        value = data.get(key)
        if not value or value == "" or value is None:
            user_input = input(f"\n⚠️  '{label}' missing hai — value do (ya Enter dabao skip karne ke liye): ").strip()
            if user_input:
                data[key] = user_input
                filled_fields[label] = user_input
            else:
                data[key] = ""

    # Jo values dii — ek baar dikhao
    if filled_fields:
        print("\n📝 Tumne yeh values dii hain:")
        print("-" * 40)
        for label, value in filled_fields.items():
            print(f"  {label:15}: {value}")
        print("-" * 40)
        recheck = input("Sahi hai? (y/n): ").strip().lower()
        if recheck != "y":
            for key, label in FIELDS:
                if label in filled_fields:
                    user_input = input(f"  {label} dobara daalo: ").strip()
                    data[key] = user_input

    return data


def retry_failed(sheet_id):
    backup = load_backup()

    if not backup:
        print("✅ Koi failed entry nahi hai — sab clear hai!")
        return

    print(f"\n📋 {len(backup)} failed entries mili hain:\n")
    for i, entry in enumerate(backup, 1):
        data = entry["data"]
        print(f"  {i}. [{entry['timestamp']}] Invoice: {data.get('invoice_no') or '—'}")
        for key, label in FIELDS:
            value = data.get(key)
            if not value or value == "":
                print(f"      ⚠️  {label}: MISSING")

    print()
    success_entries = []
    failed_entries = []

    for entry in backup:
        data = entry["data"]
        invoice_no = data.get("invoice_no") or "Unknown"

        print(f"\n{'=' * 40}")
        print(f"🔄 Processing: Invoice {invoice_no}")
        print(f"{'=' * 40}")

        # Missing fields fill karo
        data = fill_missing_fields(data)

        try:
            save_to_sheet(data, sheet_id)

            # Log mein add karo
            log = load_log(sheet_id)
            log_key = f"retry_{invoice_no}_{entry['timestamp']}"
            log[log_key] = {"status": "success", "data": data}
            save_log(log, sheet_id)

            success_entries.append(entry)
            print(f"✅ Invoice {invoice_no} — sheet mein save ho gaya!")

        except Exception as e:
            failed_entries.append(entry)
            print(f"❌ Invoice {invoice_no} — phir se fail: {str(e)}")

        time.sleep(1)

    # Backup update karo
    save_backup(failed_entries)

    print("\n" + "=" * 50)
    print("📋 RETRY COMPLETE — Summary:")
    print(f"   ✅ Saved   : {len(success_entries)}")
    print(f"   ❌ Failed  : {len(failed_entries)}")
    if not failed_entries:
        print("   🎉 failed_saves.json ab empty hai!")
    print("=" * 50)


if __name__ == "__main__":
    print("🔑 Sheet ID daalo:")
    sheet_id = input("Sheet ID: ").strip()
    if not sheet_id:
        print("❌ Sheet ID empty hai!")
    else:
        retry_failed(sheet_id)