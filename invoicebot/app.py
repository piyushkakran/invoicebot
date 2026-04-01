from flask import Flask, request, jsonify
import os
from PIL import Image
import pytesseract
import io

app = Flask(__name__)

@app.route("/")
def home():
    return "InvoiceBot Running"

@app.route("/extract", methods=["POST"])
def extract():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    file = request.files["image"]
    image = Image.open(io.BytesIO(file.read()))
    text = pytesseract.image_to_string(image)
    
    return jsonify({"extracted_text": text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)