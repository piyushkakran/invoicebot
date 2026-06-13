import json
import os
class invoice:
    def __init__(self,transport_name,bill,date,truck_number):
        self.transport_name = transport_name
        self.bill = bill
        self.date = date
        self.truck_number = truck_number
    def display(self):
        print(f"transport name:{self.transport_name}")  
        print(f"bill:{self.bill}")   
        print(f"date:{self.date}")   
        print(f"truck_number:{self.truck_number}")  
    def save_to_json(self):
        data = {
            "transport_name":self.transport_name,
            "bill":self.bill,
            "date":self.date,
            "truck_number":self.truck_number
        }
        with open("invoices.json","a") as f:
            json.dump(data,f)
            f.write("\n")
class driver:
    def __init__(self,name,phone,truck_number):
        self.name = name
        self.phone = phone
        self.truck_number = truck_number
    def display(self):
        print(f"Driver name : {self.name}")
        print(f"phone:{self.phone}")
        print(f"truck.number:{self.truck_number}")
    def save_to_json(self):
        data = {
            "name":self.name,
            "phone":self.phone,
          "truck_number":self.truck_number
        }
        with open("driver.json","a") as f:
            json.dump(data,f)
            f.write("\n")            
invoice1 =invoice("Goyal Transport",18000,"07-03-2025","HR22-9999") 
driver1 = driver("Vijay Kumar","9876543210","HR22-99999")
invoice1.display()
invoice1.save_to_json()
driver1.display()
driver1.save_to_json()
print("invoice aur driver linked hai : HR22-9999")                 

        