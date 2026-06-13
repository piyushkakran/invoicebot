import openpyxl
import json

wb = openpyxl.Workbook()
ws = wb.active

# header
ws.append(["name","phone","truck_number"])

with open("driver.json","r") as f:
    for line in f:
        data = json.loads(line)

        ws.append([
            data["name"],
            data["phone"],
            data["truck_number"]
        ])

wb.save("drivers.xlsx")

print("Driver excel file ban gyi 🚀")