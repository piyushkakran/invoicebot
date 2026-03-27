from flask import Flask
app = Flask(__name__)
@app.route("/")
def home():
    return "invoice running!"
@app.route("/invoice")
def invoice():
    return "invoice endpoint ready"
@app.route("/status")
def invoice_status():
    return " transport business ki seva mein!"
if __name__ == "__main__":
   app.run(debug = True)