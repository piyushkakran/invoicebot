from flask import Flask, request, jsonify
from gemini_test import extract_only, save_to_sheet, DuplicateInvoiceError
import os
import requests
import json
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

# In-memory pending data store
pending_sessions = {}

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


def format_extracted_data(data):
    lines = ["✅ *Invoice Extract Hua!*\n"]
    for i, (key, label) in enumerate(FIELDS, 1):
        value = data.get(key) or "⚠️ MISSING"
        lines.append(f"{i}. {label}: {value}")
    lines.append("\n✅ Sahi hai? *OK* bhejo")
    lines.append("✏️ Koi field change karni hai? *CHANGE 3* bhejo (field number ke saath)")
    lines.append("❌ Save nahi karna? *CANCEL* bhejo")
    return "\n".join(lines)


def check_month_change(phone, token):
    client = get_client(phone)
    if not client:
        return False
    current_month = datetime.now().strftime("%Y-%m")
    if client.get("month") != current_month:
        send_whatsapp_message(
            phone,
            f"📅 Naya mahina! ({current_month})\n\n"
            f"1️⃣ Nayi sheet: SHEET: <id>\n"
            f"2️⃣ Purani sheet: SAME",
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

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = message["from"]

        # ✅ Text message handling
        if message["type"] == "text":
            text = message["text"]["body"].strip()

            # SHEET command
            if text.upper().startswith("SHEET:"):
                sheet_id = text[6:].strip()
                set_client(phone, sheet_id)
                send_whatsapp_message(phone, "✅ Sheet ID save ho gayi!\nAb invoice photos bhejo 📊", token)
                return jsonify({"status": "sheet_saved"}), 200

            # SAME command
            elif text.upper() == "SAME":
                client = get_client(phone)
                if client:
                    clients = load_clients()
                    clients[phone]["month"] = datetime.now().strftime("%Y-%m")
                    save_clients(clients)
                    send_whatsapp_message(phone, "✅ Purani sheet continue!\nInvoice bhejo 📸", token)
                return jsonify({"status": "same_sheet"}), 200

            # OK — save karo
            elif text.upper() == "OK":
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ Koi pending invoice nahi hai.\nPehle invoice photo bhejo!", token)
                    return jsonify({"status": "no_pending"}), 200

                try:
                    save_to_sheet(session["data"], session["sheet_id"])
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Google Sheet mein save ho gaya!", token)
                except DuplicateInvoiceError:
                    send_whatsapp_message(
                        phone,
                        "⚠️ Yeh invoice already save hai!\n\nPhir bhi save karein? *DUPLICATE_OK* bhejo\nCancel karein? *CANCEL* bhejo",
                        token
                    )
                return jsonify({"status": "saved"}), 200

            # DUPLICATE_OK
            elif text.upper() == "DUPLICATE_OK":
                session = pending_sessions.get(phone)
                if session:
                    save_to_sheet(session["data"], session["sheet_id"], allow_duplicate=True)
                    del pending_sessions[phone]
                    send_whatsapp_message(phone, "✅ Duplicate — phir bhi save ho gaya!", token)
                return jsonify({"status": "duplicate_saved"}), 200

            # CANCEL
            elif text.upper() == "CANCEL":
                if phone in pending_sessions:
                    del pending_sessions[phone]
                send_whatsapp_message(phone, "❌ Invoice cancel kar diya.", token)
                return jsonify({"status": "cancelled"}), 200

            # CHANGE <number> <new_value>
            elif text.upper().startswith("CHANGE"):
                session = pending_sessions.get(phone)
                if not session:
                    send_whatsapp_message(phone, "⚠️ Koi pending invoice nahi.\nPehle invoice photo bhejo!", token)
                    return jsonify({"status": "no_pending"}), 200

                parts = text.split(" ", 2)
                if len(parts) == 2:
                    # Sirf number diya — bot poochega value
                    try:
                        field_num = int(parts[1])
                        if 1 <= field_num <= len(FIELDS):
                            key, label = FIELDS[field_num - 1]
                            pending_sessions[phone]["waiting_for"] = key
                            pending_sessions[phone]["waiting_label"] = label
                            send_whatsapp_message(phone, f"✏️ {label} ka naya value bhejo:", token)
                        else:
                            send_whatsapp_message(phone, "❌ Galat number! 1-9 ke beech daalo.", token)
                    except ValueError:
                        send_whatsapp_message(phone, "❌ Format: CHANGE 3\nYa: CHANGE 3 naya_value", token)
                    return jsonify({"status": "waiting_value"}), 200

                elif len(parts) == 3:
                    # Number aur value dono diye
                    try:
                        field_num = int(parts[1])
                        new_value = parts[2].strip()
                        if 1 <= field_num <= len(FIELDS):
                            key, label = FIELDS[field_num - 1]
                            pending_sessions[phone]["data"][key] = new_value
                            send_whatsapp_message(
                                phone,
                                f"✅ {label} update hua: {new_value}\n\n" + format_extracted_data(pending_sessions[phone]["data"]),
                                token
                            )
                        else:
                            send_whatsapp_message(phone, "❌ Galat number!", token)
                    except ValueError:
                        send_whatsapp_message(phone, "❌ Format: CHANGE 3 naya_value", token)
                    return jsonify({"status": "field_changed"}), 200

            # Waiting for value after CHANGE <num>
            elif phone in pending_sessions and pending_sessions[phone].get("waiting_for"):
                key = pending_sessions[phone]["waiting_for"]
                label = pending_sessions[phone]["waiting_label"]
                pending_sessions[phone]["data"][key] = text
                del pending_sessions[phone]["waiting_for"]
                del pending_sessions[phone]["waiting_label"]
                send_whatsapp_message(
                    phone,
                    f"✅ {label} update hua: {text}\n\n" + format_extracted_data(pending_sessions[phone]["data"]),
                    token
                )
                return jsonify({"status": "value_updated"}), 200

            # Koi aur text
            else:
                client = get_client(phone)
                if not client:
                    send_whatsapp_message(
                        phone,
                        "👋 InvoiceBot mein swagat!\n\nPehle sheet ID bhejo:\nSHEET: <your_sheet_id>",
                        token
                    )
                else:
                    send_whatsapp_message(phone, "📸 Invoice ki photo bhejo!", token)
                return jsonify({"status": "instructions_sent"}), 200

        # ✅ Image handling
        if message["type"] == "image":
            client = get_client(phone)
            if not client:
                send_whatsapp_message(phone, "⚠️ Pehle sheet ID bhejo:\nSHEET: <your_sheet_id>", token)
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
                send_whatsapp_message(phone, "❌ Image download nahi hui — dobara bhejo.", token)
                return jsonify({"error": "Image URL nahi mili"}), 500

            image_response = requests.get(image_url, headers={"Authorization": f"Bearer {token}"})
            image_path = f"temp_{phone}.jpg"
            with open(image_path, "wb") as f:
                f.write(image_response.content)

            try:
                result = extract_only(image_path=image_path)
            except Exception as e:
                send_whatsapp_message(phone, "❌ Invoice read nahi hua — dobara bhejo.", token)
                return jsonify({"error": str(e)}), 500

            # Pending session mein store karo
            pending_sessions[phone] = {
                "data": result,
                "sheet_id": sheet_id
            }

            # Data dikhao aur confirm maango
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