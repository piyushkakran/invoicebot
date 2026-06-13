import os
import json
from gemini_test import extract_only

# Supported image formats
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")

# Fields jo hone chahiye
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


def get_invoice_folder(sheet_id):
    folder = f"invoices_{sheet_id[:8]}"
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"📁 Naya folder banaya: {folder}")
    return folder


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


def display_and_confirm(data):
    print("\n📋 Extracted Data:")
    print("-" * 40)

    for key, label in FIELDS:
        value = data.get(key)
        if not value or value == "":
            print(f"  ⚠️  {label:15}: MISSING")
        else:
            print(f"  ✅ {label:15}: {value}")

    print("-" * 40)

    # Missing fields fill karo
    filled_fields = {}
    for key, label in FIELDS:
        value = data.get(key)
        if not value or value == "":
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
                    filled_fields[label] = user_input

    # Koi aur change karna hai?
    changed_fields = {}
    while True:
        change = input("\n🔄 Koi field change karni hai? (y/n): ").strip().lower()
        if change != "y":
            break

        print("\nKaunsa field change karna hai?")
        for i, (key, label) in enumerate(FIELDS, 1):
            print(f"  {i}. {label:15}: {data.get(key) or '—'}")

        try:
            choice = int(input("Number daalo: ").strip())
            if 1 <= choice <= len(FIELDS):
                key, label = FIELDS[choice - 1]
                new_value = input(f"Naya value daalo ({label}): ").strip()
                changed_fields[label] = {"purana": data.get(key) or "—", "naya": new_value}
                data[key] = new_value
            else:
                print("❌ Galat number!")
        except Exception:
            print("❌ Galat input!")

    # Changed fields dikhao
    if changed_fields:
        print("\n✏️  Changed Fields:")
        print("-" * 40)
        for label, values in changed_fields.items():
            print(f"  {label:15}: {values['purana']} → {values['naya']}")
        print("-" * 40)

    # Confirm karo
    confirm = input("\n✅ Sheet mein save karein? (y/n): ").strip().lower()
    return confirm == "y", data


def run_batch(sheet_id):
    from gemini_test import save_to_sheet, DuplicateInvoiceError

    INVOICES_FOLDER = get_invoice_folder(sheet_id)

    print("=" * 50)
    print("📂 Batch Invoice Tester Starting...")
    print("=" * 50)

    all_files = [
        f for f in os.listdir(INVOICES_FOLDER)
        if f.lower().endswith(IMAGE_EXTENSIONS)
    ]

    if not all_files:
        print(f"❌ Koi image nahi mili — images daalo: {INVOICES_FOLDER}/")
        return

    log = load_log(sheet_id)
    new_files = [f for f in all_files if f not in log]
    already_done = len(all_files) - len(new_files)

    print(f"📊 Total images  : {len(all_files)}")
    print(f"✅ Already done  : {already_done}")
    print(f"🆕 New to process: {len(new_files)}")
    print(f"📁 Folder        : {INVOICES_FOLDER}/")
    print(f"📝 Log file      : {get_log_file(sheet_id)}")
    print("-" * 50)

    if not new_files:
        print("🎉 Sab invoices already process ho chuki hain!")
        return

    success_count = 0
    skipped_count = 0
    failed_files = []

    for filename in new_files:
        image_path = os.path.join(INVOICES_FOLDER, filename)
        print(f"\n🔄 Processing: {filename}")

        try:
            data = extract_only(image_path=image_path)
            confirmed, final_data = display_and_confirm(data)

            if confirmed:
                try:
                    save_to_sheet(final_data, sheet_id)
                    log[filename] = {"status": "success", "data": final_data}
                    success_count += 1
                    print(f"✅ Saved to sheet!")
                except DuplicateInvoiceError as e:
                    print(f"\n⚠️  {str(e)}")
                    choice = input("Phir bhi save karein? (y/n): ").strip().lower()
                    if choice == "y":
                        save_to_sheet(final_data, sheet_id, allow_duplicate=True)
                        log[filename] = {"status": "success", "data": final_data}
                        success_count += 1
                        print(f"✅ Duplicate — phir bhi saved!")
                    else:
                        log[filename] = {"status": "skipped_duplicate"}
                        skipped_count += 1
                        print(f"⏭️  Duplicate skip kiya.")
            else:
                log[filename] = {"status": "skipped"}
                skipped_count += 1
                print(f"⏭️  Skipped.")

        except Exception as e:
            log[filename] = {"status": "failed", "error": str(e)}
            failed_files.append(filename)
            print(f"❌ Failed: {str(e)}")

        save_log(log, sheet_id)

    print("\n" + "=" * 50)
    print("📋 BATCH COMPLETE — Summary:")
    print(f"   ✅ Saved   : {success_count}")
    print(f"   ⏭️  Skipped : {skipped_count}")
    print(f"   ❌ Failed  : {len(failed_files)}")
    print("=" * 50)


if __name__ == "__main__":
    print("🔑 Sheet ID daalo:")
    sheet_id = input("Sheet ID: ").strip()
    if not sheet_id:
        print("❌ Sheet ID empty hai!")
    else:
        run_batch(sheet_id)