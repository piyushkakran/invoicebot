from flask import Flask, request, jsonify
from gemini_test import (
    extract_only,
    save_to_sheet,
    DuplicateInvoiceError,
    detect_schema_from_photo
)
import os 
import requests
import json
import re
from datetime import datetime

app = Flask(__name__)

CLIENTS_FILE = "clients.json"

pending_sessions = {}
pending_schema_detection = {}
pending_sheet_change = {}
processed_message_ids = set()

DEFAULT_CLIENTS = {
    "919991997358": {
        "sheet_id": "1WKFiRahwi8V6JxoU1ZmIUqXqFnAVDZvY0uuyf0c3I40",
        "month": "2026-06",
        "fields": ["Invoice No", "Date", "Description", "From", "To", "GST No", "Lorry No", "Amount", "Grand Total"],
        "onboarding_state": None
    }
}


def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, "r") as f:
            loaded = json.load(f)
        for phone, default in DEFAULT_CLIENTS.items():
            if phone not in loaded or "fields" not in loaded.get(phone, {}):
                loaded[phone] = default
        return loaded
    return DEFAULT_CLIENTS.copy()


def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)


def get_client(phone):
    return load_clients().get(phone)


def set_client(phone, sheet_id, keep_schema=False):
    clients = load_clients()
    if phone not in clients:
        clients[phone] = {}
    clients[phone]["sheet_id"] = sheet_id
    clients[phone]["month"] = datetime.now().strftime("%Y-%m")
    if not keep_schema:
        clients[phone]["fields"] = None
        clients[phone]["onboarding_state"] = "awaiting_mode"
    save_clients(clients)


def set_onboarding_state(phone, state):
    clients = load_clients()
    if phone in clients:
        clients[phone]["onboarding_state"] = state
    else:
        clients[phone] = {"onboarding_state": state}
    save_clients(clients)


def get_client_fields(phone):
    client = get_client(phone)
    return client.get("fields") if client else None


def set_client_fields(phone, fields_list):
    clients = load_clients()
    if phone in clients:
        clients[phone]["fields"] = [f.strip() for f in fields_list if f.strip()]
        clients[phone]["onboarding_state"] = None
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


def send_button_message(phone, body_text, buttons, token):
    """
    Sends a WhatsApp interactive message with up to 3 tappable buttons.
    'buttons' is a list of (id, title) tuples. Title must be 20 chars or less.
    The button's 'id' is what comes back in the webhook when the user taps it.
    """
    phone_id = os.environ.get("PHONE_NUMBER_ID")
    button_objects = [
        {"type": "reply", "reply": {"id": btn_id, "title": btn_title[:20]}}
        for btn_id, btn_title in buttons[:3]
    ]
    requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json={
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": button_objects}
            }
        }
    )


def handle_onboarding(phone, text, token, is_image=False):
    client = get_client(phone)
    state = client.get("onboarding_state") if client else None
    if not state:
        return False

    text_upper = (text or "").strip().upper()

    if state == "awaiting_mode":
        if "MANUAL" in text_upper:
            set_onboarding_state(phone, "awaiting_manual_fields")
            send_whatsapp_message(phone, "✏️ Comma-separated field names bhejo (e.g. Invoice No, Date, Lorry No, Amount, From, To)", token)
            return True
        elif "PHOTO" in text_upper:
            set_onboarding_state(phone, "awaiting_photo")
            send_whatsapp_message(phone, "📸 Apni Excel/register ki photo bhejo (column headers ke saath)", token)
            return True
        else:
            send_whatsapp_message(phone, "❌ MANUAL ya PHOTO likho", token)
            return True

    elif state == "awaiting_manual_fields":
        fields = [f.strip() for f in text.split(",") if f.strip()]
        if len(fields) < 2:
            send_whatsapp_message(phone, "❌ Kam se kam 2 fields chahiye. Dobara bhejo.", token)
            return True
        set_client_fields(phone, fields)
        send_whatsapp_message(phone, f"✅ Fields set ho gaye!\n{', '.join(fields)}\n\nAb invoice photos bhej sakte ho 📸", token)
        return True

    elif state == "awaiting_photo":
        if not is_image:
            if "MANUAL" in text_upper:
                set_onboarding_state(phone, "awaiting_manual_fields")
                send_whatsapp_message(phone, "✏️ Comma-separated field names bhejo", token)
            else:
                send_whatsapp_message(phone, "📸 Photo bhejo ya MANUAL likho", token)
            return True
        return False

    elif state == "awaiting_photo_confirm":
        if "CONFIRM" in text_upper:
            detected = pending_schema_detection.get(phone)
            if detected:
                set_client_fields(phone, detected)
                send_whatsapp_message(phone, f"✅ Fields confirmed!\n{', '.join(detected)}\n\nAb invoice photos bhej sakte ho 📸", token)
                pending_schema_detection.pop(phone, None)
            return True
        elif text_upper.startswith("CHANGE "):
            new_fields = [f.strip() for f in text[7:].split(",") if f.strip()]
            if len(new_fields) >= 2:
                set_client_fields(phone, new_fields)
                pending_schema_detection.pop(phone, None)
                send_whatsapp_message(phone, f"✅ Fields updated!\n{', '.join(new_fields)}\n\nAb invoice photos bhej sakte ho 📸", token)
            return True
        return False

    elif state == "awaiting_schema_change":
        fields = [f.strip() for f in text.split(",") if f.strip()] if text else []
        if len(fields) >= 2:
            set_client_fields(phone, fields)
            send_whatsapp_message(phone, f"✅ Schema updated!\n{', '.join(fields)}", token)
        return True

    elif state == "awaiting_schema_reuse_choice":
        if "SAME SCHEMA" in text_upper:
            sheet_id = pending_sheet_change.pop(phone, None)
            if sheet_id:
                clients = load_clients()
                clients[phone]["sheet_id"] = sheet_id
                clients[phone]["month"] = datetime.now().strftime("%Y-%m")
                clients[phone]["onboarding_state"] = None
                save_clients(clients)
                send_whatsapp_message(phone, "✅ Same schema with new sheet activated!", token)
            return True
        elif "NEW SCHEMA" in text_upper:
            sheet_id = pending_sheet_change.pop(phone, None)
            if sheet_id:
                set_client(phone, sheet_id, keep_schema=False)
                send_whatsapp_message(phone, "MANUAL ya PHOTO bhejo for new schema", token)
            return True
        return False

    return False


def format_extracted_data(data, client_fields):
    """Returns just the numbered field list. Confirm/Change/Cancel are now
    presented as buttons (see send_invoice_confirm_buttons), not as text."""
    lines = ["✅ *Invoice Extract Hua!*\n"]
    for i, label in enumerate(client_fields, 1):
        key = label.lower().replace(" ", "_")
        value = data.get(key) or "⚠️ MISSING"
        lines.append(f"{i}. {label}: {value}")
    return "\n".join(lines)


def send_invoice_confirm_buttons(phone, data, client_fields, token):
    """Sends the extracted invoice data with OK / Change / Cancel buttons."""
    body = format_extracted_data(data, client_fields)
    send_button_message(
        phone,
        body,
        [("INVOICE_OK", "✅ OK"), ("INVOICE_CHANGE", "✏️ Change"), ("INVOICE_CANCEL", "❌ Cancel")],
        token
    )


def get_missing_fields(data, client_fields):
    missing = []
    for i, label in enumerate(client_fields, 1):
        key = label.lower().replace(" ", "_")
        value = data.get(key)
        if not value or str(value).strip() == "":
            missing.append((i, key, label))
    return missing


def _is_valid_field_number(token, field_count):
    """Check whether a token is an integer within the valid field range."""
    try:
        num = int(token)
        return 1 <= num <= field_count
    except ValueError:
        return False


def _line_is_ambiguous(line, field_count):
    """
    A single line is ambiguous if it contains more than one token that could
    be a valid field number, since we can't tell whether a later number is
    part of the previous field's value or a new field marker.
    """
    tokens = line.strip().split(" ")
    if not tokens:
        return False
    # Skip the first token (it's the field number for this line), check the rest
    number_like_tokens = [t for t in tokens[1:] if _is_valid_field_number(t, field_count)]
    return len(number_like_tokens) > 0


def process_change_lines(text, data, client_fields):
    """
    Parses change instructions without requiring the word CHANGE.
    Accepts lines like:
        1 25000
        3 Mumbai
    Each line must be: <field_number> <value...>
    If a line has extra number tokens that could also be field markers,
    it's treated as ambiguous and skipped, with a note returned to the caller.
    """
    field_count = len(client_fields) if client_fields else 0
    lines = [l for l in text.strip().split("\n") if l.strip()]
    updates = []
    ambiguous_lines = []

    for line in lines:
        line = line.strip()
        tokens = line.split(" ", 1)
        if len(tokens) < 2:
            continue

        field_token, rest = tokens[0], tokens[1].strip()
        if not _is_valid_field_number(field_token, field_count):
            continue

        if _line_is_ambiguous(line, field_count):
            ambiguous_lines.append(line)
            continue

        field_num = int(field_token)
        label = client_fields[field_num - 1]
        key = label.lower().replace(" ", "_")
        data[key] = rest
        updates.append((label, rest))

    return data, updates, ambiguous_lines


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

    WELCOME_MESSAGE_PART2 = "invoicebot-sheets@invoicebot2-493606.iam.gserviceaccount.com"

    WELCOME_MESSAGE_PART3 = """4️⃣ Copy your Sheet link
5️⃣ Send it here as: SHEET: <link>"""

    def send_welcome(phone, token):
        send_whatsapp_message(phone, WELCOME_MESSAGE_PART1, token)
        send_whatsapp_message(phone, WELCOME_MESSAGE_PART2, token)
        send_whatsapp_message(phone, WELCOME_MESSAGE_PART3, token)

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

        # Text message handling
        if message["type"] == "text":
            text = message["text"]["body"].strip()
            text_upper = text.upper()

            # SHEET command
            if text_upper.startswith("SHEET:"):
                sheet_id = extract_sheet_id(text[6:].strip())
                client = get_client(phone)
                if client and client.get("fields"):
                    pending_sheet_change[phone] = sheet_id
                    set_onboarding_state(phone, "awaiting_schema_reuse_choice")
                    send_button_message(
                        phone,
                        "Aapka purana schema use karna hai?",
                        [("SCHEMA_SAME", "Same schema"), ("SCHEMA_NEW", "New schema")],
                        token
                    )
                else:
                    set_client(phone, sheet_id)
                    send_button_message(
                        phone,
                        "✅ Sheet linked! Schema set karne ke liye option choose karo:",
                        [("MODE_MANUAL", "✏️ Manual"), ("MODE_PHOTO", "📸 Photo")],
                        token
                    )
                return jsonify({"status": "sheet_saved"}), 200

            # CHANGE FIELDS
            if text_upper.startswith("CHANGE FIELDS"):
                set_onboarding_state(phone, "awaiting_schema_change")
                send_whatsapp_message(phone, "✏️ Naya comma-separated fields list bhejo", token)
                return jsonify({"status": "change_fields"}), 200

            # SAME command
            if text_upper == "SAME":
                client = get_client(phone)
                if client:
                    clients = load_clients()
                    clients[phone]["month"] = datetime.now().strftime("%Y-%m")
                    save_clients(clients)
                    send_whatsapp_message(phone, "✅ Continuing with same sheet!\nSend invoice photos 📸", token)
                return jsonify({"status": "same_sheet"}), 200

            # OK
            if text_upper == "OK":
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ No pending invoice.\nSend an invoice photo first!", token)
                    return jsonify({"status": "no_pending"}), 200
                client_fields = get_client_fields(phone)
                missing = get_missing_fields(session["data"], client_fields)
                if missing:
                    send_whatsapp_message(phone, "Kuch fields missing hain. Field number aur value bhejo, jaise: 1 25000", token)
                    return jsonify({"status": "still_missing"}), 200
                try:
                    save_to_sheet(session["data"], session["sheet_id"], client_fields=client_fields)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved to Google Sheet!", token)
                except DuplicateInvoiceError:
                    send_button_message(
                        phone,
                        "⚠️ This invoice already exists! Save anyway?",
                        [("DUPLICATE_YES", "Yes, save"), ("DUPLICATE_NO", "No, cancel")],
                        token
                    )
                return jsonify({"status": "saved"}), 200

            # DUPLICATE_OK
            if text_upper == "DUPLICATE_OK":
                session = pending_sessions.get(phone)
                if session:
                    client_fields = get_client_fields(phone)
                    save_to_sheet(session["data"], session["sheet_id"], allow_duplicate=True, client_fields=client_fields)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved (duplicate allowed)!", token)
                return jsonify({"status": "duplicate_saved"}), 200

            # CANCEL
            if text_upper == "CANCEL":
                if phone in pending_sessions:
                    del pending_sessions[phone]
                send_whatsapp_message(phone, "❌ Invoice cancelled.", token)
                return jsonify({"status": "cancelled"}), 200

            # Field update for a pending invoice (no CHANGE word needed)
            # Triggered when there's a pending session and the message looks
            # like "<field_number> <value>" on one or more lines.
            session = pending_sessions.get(phone)
            first_line = text.strip().split("\n")[0].strip()
            first_token = first_line.split(" ", 1)[0] if first_line else ""
            looks_like_field_update = (
                session is not None
                and _is_valid_field_number(first_token, len(get_client_fields(phone) or []))
            )

            if looks_like_field_update:
                client_fields = get_client_fields(phone)
                updated_data, updates, ambiguous_lines = process_change_lines(text, session["data"], client_fields)

                if ambiguous_lines:
                    send_whatsapp_message(
                        phone,
                        "❌ Yeh line samajh nahi aayi (ek se zyada number ho sakte hain):\n"
                        + "\n".join(ambiguous_lines)
                        + "\n\nHar field ko alag line mein bhejo, jaise:\n1 25000\n3 Mumbai",
                        token
                    )
                    return jsonify({"status": "ambiguous_update"}), 200

                if not updates:
                    send_whatsapp_message(phone, "❌ Format samajh nahi aaya. Bhejo: <field number> <value>\nJaise: 1 25000", token)
                    return jsonify({"status": "no_updates"}), 200

                pending_sessions[phone]["data"] = updated_data
                send_invoice_confirm_buttons(phone, updated_data, client_fields, token)
                return jsonify({"status": "field_changed"}), 200

            # Handle onboarding
            client = get_client(phone)
            if client and client.get("onboarding_state"):
                if handle_onboarding(phone, text, token):
                    return jsonify({"status": "onboarding"}), 200

            # Default text
            if not client:
                send_welcome(phone, token)
            else:
                send_whatsapp_message(phone, "📸 Send invoice photo!", token)
            return jsonify({"status": "instructions_sent"}), 200

        # Interactive button reply handling
        if message["type"] == "interactive":
            interactive_data = message.get("interactive", {})
            if interactive_data.get("type") != "button_reply":
                return jsonify({"status": "unsupported_interactive"}), 200

            button_id = interactive_data.get("button_reply", {}).get("id", "")

            # Mode select during onboarding
            if button_id == "MODE_MANUAL":
                set_onboarding_state(phone, "awaiting_manual_fields")
                send_whatsapp_message(phone, "✏️ Comma-separated field names bhejo (e.g. Invoice No, Date, Lorry No, Amount, From, To)", token)
                return jsonify({"status": "onboarding"}), 200

            if button_id == "MODE_PHOTO":
                set_onboarding_state(phone, "awaiting_photo")
                send_whatsapp_message(phone, "📸 Apni Excel/register ki photo bhejo (column headers ke saath)", token)
                return jsonify({"status": "onboarding"}), 200

            # Invoice confirm: OK / Change / Cancel
            if button_id == "INVOICE_OK":
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ No pending invoice.\nSend an invoice photo first!", token)
                    return jsonify({"status": "no_pending"}), 200
                client_fields = get_client_fields(phone)
                missing = get_missing_fields(session["data"], client_fields)
                if missing:
                    send_whatsapp_message(phone, "Kuch fields missing hain. Field number aur value bhejo, jaise: 1 25000", token)
                    return jsonify({"status": "still_missing"}), 200
                try:
                    save_to_sheet(session["data"], session["sheet_id"], client_fields=client_fields)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved to Google Sheet!", token)
                except DuplicateInvoiceError:
                    send_button_message(
                        phone,
                        "⚠️ This invoice already exists! Save anyway?",
                        [("DUPLICATE_YES", "Yes, save"), ("DUPLICATE_NO", "No, cancel")],
                        token
                    )
                return jsonify({"status": "saved"}), 200

            if button_id == "INVOICE_CHANGE":
                send_whatsapp_message(phone, "✏️ Field number aur sahi value bhejo, jaise:\n1 25000\n3 Mumbai", token)
                return jsonify({"status": "awaiting_change_input"}), 200

            if button_id == "INVOICE_CANCEL":
                if phone in pending_sessions:
                    del pending_sessions[phone]
                send_whatsapp_message(phone, "❌ Invoice cancelled.", token)
                return jsonify({"status": "cancelled"}), 200

            # Duplicate confirm: Yes / No
            if button_id == "DUPLICATE_YES":
                session = pending_sessions.get(phone)
                if session:
                    client_fields = get_client_fields(phone)
                    save_to_sheet(session["data"], session["sheet_id"], allow_duplicate=True, client_fields=client_fields)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Saved (duplicate allowed)!", token)
                return jsonify({"status": "duplicate_saved"}), 200

            if button_id == "DUPLICATE_NO":
                if phone in pending_sessions:
                    del pending_sessions[phone]
                send_whatsapp_message(phone, "❌ Invoice cancelled.", token)
                return jsonify({"status": "cancelled"}), 200

            # Schema reuse choice: Same / New
            if button_id == "SCHEMA_SAME":
                sheet_id = pending_sheet_change.pop(phone, None)
                if sheet_id:
                    clients = load_clients()
                    clients[phone]["sheet_id"] = sheet_id
                    clients[phone]["month"] = datetime.now().strftime("%Y-%m")
                    clients[phone]["onboarding_state"] = None
                    save_clients(clients)
                    send_whatsapp_message(phone, "✅ Same schema with new sheet activated!", token)
                return jsonify({"status": "schema_same"}), 200

            if button_id == "SCHEMA_NEW":
                sheet_id = pending_sheet_change.pop(phone, None)
                if sheet_id:
                    set_client(phone, sheet_id, keep_schema=False)
                    send_button_message(
                        phone,
                        "Naya schema set karne ke liye option choose karo:",
                        [("MODE_MANUAL", "✏️ Manual"), ("MODE_PHOTO", "📸 Photo")],
                        token
                    )
                return jsonify({"status": "schema_new"}), 200

            # Schema detection confirm: Confirm / re-do via manual
            if button_id == "SCHEMA_CONFIRM":
                detected = pending_schema_detection.get(phone)
                if detected:
                    set_client_fields(phone, detected)
                    send_whatsapp_message(phone, f"✅ Fields confirmed!\n{', '.join(detected)}\n\nAb invoice photos bhej sakte ho 📸", token)
                    pending_schema_detection.pop(phone, None)
                return jsonify({"status": "schema_confirmed"}), 200

            if button_id == "SCHEMA_REDO":
                set_onboarding_state(phone, "awaiting_manual_fields")
                pending_schema_detection.pop(phone, None)
                send_whatsapp_message(phone, "✏️ Comma-separated field names bhejo (e.g. Invoice No, Date, Lorry No, Amount, From, To)", token)
                return jsonify({"status": "schema_redo"}), 200

            return jsonify({"status": "unknown_button"}), 200

        # Image handling
        if message["type"] == "image":
            client = get_client(phone)
            if not client:
                send_welcome(phone, token)
                return jsonify({"status": "no_sheet_id"}), 200

            state = client.get("onboarding_state")

            # Wrong state image
            if state and state not in ["awaiting_photo", "awaiting_photo_confirm"]:
                send_whatsapp_message(phone, "Abhi photo nahi, pehle diye gaye option choose karo ya text bhejo.", token)
                return jsonify({"status": "onboarding_text_expected"}), 200

            # Schema detection photo
            if state in ["awaiting_photo", "awaiting_photo_confirm"]:
                media_id = message["image"]["id"]
                url_response = requests.get(
                    f"https://graph.facebook.com/v19.0/{media_id}",
                    headers={"Authorization": f"Bearer {token}"}
                )
                image_url = url_response.json().get("url")

                if not image_url:
                    send_whatsapp_message(phone, "❌ Image download failed.", token)
                    return jsonify({"error": "no_url"}), 500

                image_response = requests.get(image_url, headers={"Authorization": f"Bearer {token}"})
                image_path = f"temp_schema_{phone}.jpg"
                with open(image_path, "wb") as f:
                    f.write(image_response.content)

                try:
                    fields = detect_schema_from_photo(image_path)
                    if fields and len(fields) >= 2:
                        pending_schema_detection[phone] = fields
                        set_onboarding_state(phone, "awaiting_photo_confirm")
                        send_button_message(
                            phone,
                            f"Detected fields:\n{', '.join(fields)}",
                            [("SCHEMA_CONFIRM", "✅ Confirm"), ("SCHEMA_REDO", "✏️ Type my own")],
                            token
                        )
                    else:
                        send_whatsapp_message(phone, "❌ Fields detect nahi hue. MANUAL try karo.", token)
                except Exception as e:
                    send_whatsapp_message(phone, "❌ Photo processing failed.", token)
                finally:
                    if os.path.exists(image_path):
                        os.remove(image_path)
                return jsonify({"status": "schema_detected"}), 200

            # Normal invoice image
            if check_month_change(phone, token):
                return jsonify({"status": "month_change_pending"}), 200

            client_fields = get_client_fields(phone)
            if not client_fields:
                send_whatsapp_message(phone, "Pehle schema set karo (MANUAL ya PHOTO)", token)
                return jsonify({"status": "no_fields"}), 200

            # Download invoice image
            media_id = message["image"]["id"]
            url_response = requests.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            image_url = url_response.json().get("url")

            if not image_url:
                send_whatsapp_message(phone, "❌ Could not download image.", token)
                return jsonify({"error": "no_url"}), 500

            image_response = requests.get(image_url, headers={"Authorization": f"Bearer {token}"})
            image_path = f"temp_{phone}.jpg"
            with open(image_path, "wb") as f:
                f.write(image_response.content)

            try:
                result = extract_only(image_path=image_path, client_fields=client_fields)
            except Exception as e:
                send_whatsapp_message(phone, "❌ Could not read invoice — try again.", token)
                if os.path.exists(image_path):
                    os.remove(image_path)
                return jsonify({"error": str(e)}), 500

            pending_sessions[phone] = {
                "data": result,
                "sheet_id": client["sheet_id"]
            }

            send_invoice_confirm_buttons(phone, result, client_fields, token)

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