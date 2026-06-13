from flask import Flask, request, jsonify
import json
import openpyxl
import os
app = Flask(__name__) 
class invoice():
    def __init__(self,transport_name,amount,date,vehicle):
        self.transport_name = transport_name
        self.amount = amount
        self.date = date
        self.vehicle = vehicle
        self.GST = self.amount*0.05
    def show_display(self):
           print(f"transport_name : {self.transport_name}") 
           print(f"amount : {self.amount}")
           print(f"date : {self.date}")
           print(f"vehicle :{self.vehicle}")
           print(f"bill after GST :{self.GST}")
    def save_to_json(self):
          data = {
               "transport_name":self.transport_name,
               "amount":self.amount,
               "date":self.date,
               "vehicle":self.vehicle,
               "GST":self.GST
          } 
          with open("Invoice.json","a") as f:
               json.dump(data,f)
               f.write("\n")
               print("invoice save to json!!!") 
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
        with open("Driver.json","a") as f:
            json.dump(data,f)
            f.write("\n")
            print("driver details saved!")
inv1 = invoice("Ram Transport", 15000, "07-03-2025", "HR55-1234")
inv2 = invoice("Shyam Logistics", 22000, "07-03-2025", "HR10-5678")
driver1 =driver("rakesh kumar","9812345678","HR55-1234")
driver2 =driver("suresh singh","9876543210","HR31-1234") 
inv1.show_display()
inv1.save_to_json()

inv2.show_display()
inv2.save_to_json()
driver1.display()
driver1.save_to_json()
driver2.display()
driver2.save_to_json()

@app.route("/webhook",methods = ["POST"])
def webhook():
     data = request.json
    
     wb = openpyxl.Workbook()
    
     ws = wb.active
     ws.append(["Transport Name", "Amount", "Date", "Vehicle", "GST"])
     with open("Invoice.json","r") as f:
         for line in f:
             data = json.loads(line)
    
             ws.append(
               [
               data["transport_name"],
               data["amount"],
               data["date"],
               data["vehicle"],
               data["GST"]
             ])
     wb.save("Invoice.xlsx")
     print("done!!") 
    
    
     wb2 = openpyxl.Workbook()
     ws2 = wb2.active
     ws2.append(["Name", "Phone", "Truck Number"])

     with open("Driver.json", "r") as f:
        for line in f:
            driver = json.loads(line)
            ws2.append([
                driver["name"],
                driver["phone"],
                driver["truck_number"]
            ])
     wb2.save("Drivers.xlsx")
     return jsonify({"status":"success"})
if __name__ == "__main__":
    app.run(debug=False)
                                     
         