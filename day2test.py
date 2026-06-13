import json
import os
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
            print("driver details saved!")
driver1 =driver("rakesh kumar","9812345678","HR55-1234")
driver2 =driver("suresh singh","9876543210","HR31-1234") 
driver1.display()
driver1.save_to_json()
driver2.display()
driver2.save_to_json()          