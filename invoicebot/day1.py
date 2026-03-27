invoice = { "party_name": "ram transport","amount" : 15000 , "date":"26-02-2025","vehicle":"HR55-1234"
           }
print("Invoice starting....")
print(f"Party: {invoice['party_name']}")
print(f"Amount: ₹{invoice['amount']}")
print(f"Date: {invoice['date']}")
print(f"Vehicle: {invoice['vehicle']}")