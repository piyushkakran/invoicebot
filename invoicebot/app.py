from flask import Flask, request, jsonify
from gemini_test import extract_and_save
import os


app = Flask(__name__)



@app.route("/extract", methods=["POST"])
def extract():
    
    
    file = request.files["image"]
    file.save("temp_invoice.jpg")
    result = extract_and_save(image_path="temp_invoice.jpg")
    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)