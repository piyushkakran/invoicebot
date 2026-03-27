import json
import os

class Invoice:
    def __init__(self, party_name, amount, date, vehicle):
        self.party_name = party_name
        self.amount = amount
        self.date = date
        self.vehicle = vehicle

    def display(self):
        print(f"Party: {self.party_name}")
        print(f"Amount: ₹{self.amount}")
        print(f"Date: {self.date}")
        print(f"Vehicle: {self.vehicle}")

    def save_to_json(self):
        data = {
            "party_name": self.party_name,
            "amount": self.amount,
            "date": self.date,
            "vehicle": self.vehicle
        }
        with open("invoices.json", "a") as f:
            json.dump(data, f)
            f.write("\n")
        print("Invoice saved!")

# Test karo
inv1 = Invoice("Ram Transport", 15000, "07-03-2025", "HR55-1234")
inv2 = Invoice("Shyam Logistics", 22000, "07-03-2025", "HR10-5678")

inv1.display()
inv1.save_to_json()

inv2.display()
inv2.save_to_json()