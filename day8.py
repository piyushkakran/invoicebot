from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/whatsapp", methods=["POST", "GET"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    print(f"Message aaya: {incoming_msg}")
    
    resp = MessagingResponse()
    resp.message("InvoiceBot: Aapka message mila! 🚀")
    
    return Response(str(resp), mimetype="text/xml")

if __name__ == "__main__":
    app.run(debug=False, port=5000)