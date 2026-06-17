from flask import Flask, request, jsonify
from gemini_test import extract_only, save_to_sheet, DuplicateInvoiceError
import os
import requests
import json
import re
from datetime import datetime

app = Flask(__name__)

CLIENTS_FILE = "clients.json"

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

pending_sessions = {}
processed_message_ids = set()

DEFAULT_CLIENTS = {
    "919991997358": {
        "sheet_id": "1WKFiRahwi8V6JxoU1ZmIUqXqFnAVDZvY0uuyf0c3I40",
        "month": "2026-06"
    }
}


def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, "r") as f:
            return {**DEFAULT_CLIENTS, **json.load(f)}
    return DEFAULT_CLIENTS


def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)


def get_client(phone):
    return load_clients().get(phone)


def set_client(phone, sheet_id):
    clients = load_clients()
    clients[phone] = {
        "sheet_id": sheet_id,
        "month": datetime.now().strftime("%Y-%m")
    }
    save_clients(clients)


def extract_sheet_id(text):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', text)
    if match:
        return match.group(1)
    return text.strip()


def send_whatsapp_message(phone, message, token):
    phone_id = os.environ.get("PHONE_NUMBER_ID")
    requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message}
        }
    )


def get_missing_fields(data):
    """Return list of (index, key, label) for missing fields"""
    missing = []
    for i, (key, label) in enumerate(FIELDS, 1):
        value = data.get(key)
        if not value or str(value).strip() == "":
            missing.append((i, key, label))
    return missing


def format_missing_fields_prompt(data):
    missing = get_missing_fields(data)
    lines = ["⚠️ *Kuch fields missing hain!*\n"]
    lines.append("Extracted data:")
    for i, (key, label) in enumerate(FIELDS, 1):
        value = data.get(key) or "⚠️ MISSING"
        lines.append(f"{i}. {label}: {value}")
    lines.append("\n✏️ Missing fields fill karo:")
    for i, key, label in missing:
        lines.append(f"CHANGE {i} <value>")
    lines.append("\nExample:")
    example_lines = "\n".join([f"CHANGE {i} value{i}" for i, _, _ in missing[:2]])
    lines.append(example_lines)
    lines.append("\n(Ek message mein multiple lines bhej sakte ho)")
    return "\n".join(lines)


def format_extracted_data(data):
    missing = get_missing_fields(data)
    if missing:
        return format_missing_fields_prompt(data)

    lines = ["✅ *Invoice Extract Hua!*\n"]
    for i, (key, label) in enumerate(FIELDS, 1):
        value = data.get(key)
        lines.append(f"{i}. {label}: {value}")
    lines.append("\n✅ Sahi hai? *OK* bhejo")
    lines.append("✏️ Koi field change karni hai? *CHANGE 3 <value>* bhejo")
    lines.append("❌ Save nahi karna? *CANCEL* bhejo")
    return "\n".join(lines)


def process_change_lines(text, data):
    """Process one or more CHANGE lines, returns updated data and list of updates made"""
    lines = text.strip().split("\n")
    updates = []
    for line in lines:
        line = line.strip()
        if not line.upper().startswith("CHANGE"):
            continue
        parts = line.split(" ", 2)
        if len(parts) >= 3:
            try:
                field_num = int(parts[1])
                new_value = parts[2].strip()
                if 1 <= field_num <= len(FIELDS):
                    key, label = FIELDS[field_num - 1]
                    data[key] = new_value
                    updates.append((label, new_value))
            except ValueError:
                continue
    return data, updates


def check_month_change(phone, token):
    client = get_client(phone)
    if not client:
        return False
    current_month = datetime.now().strftime("%Y-%m")
    if client.get("month") != current_month:
        send_whatsapp_message(
            phone,
            f"📅 New month! ({current_month})\n\n"
            f"1️⃣ New sheet: SHEET: <link>\n"
            f"2️⃣ Same sheet: SAME",
            token
        )
        return True
    return False


@app.route("/whatsapp", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == "invoicebot123":
        return challenge, 200
    return "Forbidden", 403


@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    data = request.json
    token = os.environ.get("WHATSAPP_TOKEN")

    WELCOME_MESSAGE_PART1 = """👋 *Welcome to InvoiceBot!*

Setup steps:
1️⃣ Open your Google Sheet
2️⃣ Click Share
3️⃣ Add this email below with Editor access (tap and hold to copy):"""

    WELCOME_EMAIL_ONLY = "invoicebot-sheets@invoicebot2-493606.iam.gserviceaccount.com"

    WELCOME_MESSAGE_PART2 = """4️⃣ Copy your Sheet link
5️⃣ Send it here as: SHEET: <link>

That's it! Then just send invoice photos 📸"""

    def send_welcome(phone, token):
        send_whatsapp_message(phone, WELCOME_MESSAGE_PART1, token)
        send_whatsapp_message(phone, WELCOME_EMAIL_ONLY, token)
        send_whatsapp_message(phone, WELCOME_MESSAGE_PART2, token)

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]
        msg_id = message.get("id")

        if msg_id:
            if msg_id in processed_message_ids:
                return jsonify({"status": "duplicate_ignored"}), 200
            processed_message_ids.add(msg_id)
            if len(processed_message_ids) > 500:
                processed_message_ids.clear()

        if message["type"] == "text":
            text = message["text"]["body"].strip()
            text_upper = text.upper()

            # SHEET command
            if text_upper.startswith("SHEET:"):
                sheet_id = extract_sheet_id(text[6:].strip())
                set_client(phone, sheet_id)
                send_whatsapp_message(phone, "✅ Sheet linked successfully!\nNow send invoice photos 📊", token)
                return jsonify({"status": "sheet_saved"}), 200

            # SAME command
            elif text_upper == "SAME":
                client = get_client(phone)
                if client:
                    clients = load_clients()
                    clients[phone]["month"] = datetime.now().strftime("%Y-%m")
                    save_clients(clients)
                    send_whatsapp_message(phone, "✅ Continuing with same sheet!\nSend invoice photos 📸", token)
                return jsonify({"status": "same_sheet"}), 200

            # OK — save
            elif text_upper == "OK":
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ No pending invoice.\nSend an invoice photo first!", token)
                    return jsonify({"status": "no_pending"}), 200

                missing = get_missing_fields(session["data"])
                if missing:
                    send_whatsapp_message(phone, format_missing_fields_prompt(session["data"]), token)
                    return jsonify({"status": "still_missing"}), 200

                try:
                    save_to_sheet(session["data"], session["sheet_id"])
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved to Google Sheet!", token)
                except DuplicateInvoiceError:
                    send_whatsapp_message(
                        phone,
                        "⚠️ This invoice already exists!\n\nSave anyway? *DUPLICATE_OK*\nCancel? *CANCEL*",
                        token
                    )
                return jsonify({"status": "saved"}), 200

            # DUPLICATE_OK
            elif text_upper == "DUPLICATE_OK":
                session = pending_sessions.get(phone)
                if session:
                    save_to_sheet(session["data"], session["sheet_id"], allow_duplicate=True)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved (duplicate allowed)!", token)
                return jsonify({"status": "duplicate_saved"}), 200

            # CANCEL
            elif text_upper == "CANCEL":
                if phone in pending_sessions:
                    del pending_sessions[phone]
                send_whatsapp_message(phone, "❌ Invoice cancelled.", token)
                return jsonify({"status": "cancelled"}), 200

            # CHANGE (single or multi-line)
            elif text_upper.startswith("CHANGE") or "\nCHANGE" in text_upper or "\ncHANGE" in text:
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ No pending invoice.\nSend an invoice photo first!", token)
                    return jsonify({"status": "no_pending"}), 200

                updated_data, updates = process_change_lines(text, session["data"])

                if not updates:
                    send_whatsapp_message(phone, "❌ Format: CHANGE 3 <value>\n(One per line for multiple)", token)
                    return jsonify({"status": "no_updates"}), 200

                pending_sessions[phone]["data"] = updated_data

                summary = "\n".join([f"✅ {label} → {value}" for label, value in updates])
                send_whatsapp_message(
                    phone,
                    summary + "\n\n" + format_extracted_data(updated_data),
                    token
                )
                return jsonify({"status": "field_changed"}), 200

            # Other text
            else:
                client = get_client(phone)
                if not client:
                    send_welcome(phone, token)
                else:
                    send_whatsapp_message(phone, "📸 Send an invoice photo!", token)
                return jsonify({"status": "instructions_sent"}), 200

        # Image handling
        if message["type"] == "image":
            client = get_client(phone)
            if not client:
                send_welcome(phone, token)
                return jsonify({"status": "no_sheet_id"}), 200

            if check_month_change(phone, token):
                return jsonify({"status": "month_change_pending"}), 200

            sheet_id = client["sheet_id"]
            media_id = message["image"]["id"]

            url_response = requests.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            image_url = url_response.json().get("url")

            if not image_url:
                send_whatsapp_message(phone, "❌ Could not download image — try again.", token)
                return jsonify({"error": "Image URL not found"}), 500

            image_response = requests.get(image_url, headers={"Authorization": f"Bearer {token}"})
            image_path = f"temp_{phone}.jpg"
            with open(image_path, "wb") as f:
                f.write(image_response.content)

            try:
                result = extract_only(image_path=image_path)
            except Exception as e:
                send_whatsapp_message(phone, "❌ Could not read invoice — try again.", token)
                return jsonify({"error": str(e)}), 500

            pending_sessions[phone] = {
                "data": result,
                "sheet_id": sheet_id
            }

            send_whatsapp_message(phone, format_extracted_data(result), token)

            if os.path.exists(image_path):
                os.remove(image_path)

            return jsonify({"status": "extracted_waiting_confirm"}), 200

        return jsonify({"status": "ignored"}), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/extract", methods=["POST"])
def extract():
    file = request.files["image"]
    file.save("temp_invoice.jpg")
    result = extract_only(image_path="temp_invoice.jpg")
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)