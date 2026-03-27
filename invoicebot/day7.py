from twilio.rest import Client
import os

account_sid = os.environ.get('TWILIO_ACCOUNT_SID')   
auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

message = client.messages.create(
    from_='whatsapp:+14155238886',
    to='whatsapp:+918307013313',
    body='InvoiceBot ka pehla message! 🚀'
)

print(f"Message bheja! SID: {message.sid}")