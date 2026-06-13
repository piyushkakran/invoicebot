import json
import os
class invoice:
    def __init__(self,transport_name,bill,date,truck_number):
        self.transport_name = transport_name
        self.bill = bill
        self.date = date
        self.truck_number = truck_number
        self.gst = self.bill * 0.05
        self.total = self.bill +self.gst
    

    def display(self):
        print(f"transport name:{self.transport_name}")  
        print(f"bill:{self.bill}")
        print(f"gst:{self.gst}")  
        print(f"total:{self.total}") 
        print(f"date:{self.date}")   
        print(f"truck_number:{self.truck_number}")
    
    def save_to_json(self):
        data = {
            "transport_name":self.transport_name,
            "bill":self.bill,
            "gst":self.gst,
            "total":self.total,
            "date":self.date,
            "truck_number":self.truck_number
        }
        with open("invoices.json","a") as f:
            json.dump(data,f)
            f.write("\n")
invoice1 =invoice("Goyal Transport",18000,"07-03-2025","HR22-9999")
invoice1.display()
invoice1.save_to_json()            