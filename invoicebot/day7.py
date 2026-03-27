from twilio.rest import Client

account_sid = 'ACc2358f1a86e36958169d76294651f107'
auth_token = '07ffde9d3daa9e7d7ce763835b53f9af'

client = Client(account_sid, auth_token)

message = client.messages.create(
    from_='whatsapp:+14155238886',
    to='whatsapp:+918307013313',
    body='InvoiceBot ka pehla message! 🚀'
)

print(f"Message bheja! SID: {message.sid}")