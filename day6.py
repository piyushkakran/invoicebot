from flask import Flask, request, jsonify
import json
import openpyxl
import os

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    print(f"Data aaya: {data}")

    file_name = "invoices.xlsx"

    # Agar file exist nahi karti to new bana
    if not os.path.exists(file_name):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["transport_name", "amount", "date", "vehicle"])
        wb.save(file_name)

    wb = openpyxl.load_workbook(file_name)
    ws = wb.active

    ws.append([
        data["transport_name"],
        data["amount"],
        data["date"],
        data["vehicle"]
    ])

    wb.save(file_name)

    return jsonify({"status": "success", "message": "Excel mein save ho gaya!"})

if __name__ == "__main__":
    app.run(debug=True)