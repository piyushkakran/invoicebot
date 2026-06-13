import pytesseract
from PIL import Image

img = Image.open("kakran_invoice.jpg")
text = pytesseract.image_to_string(img)
print(text)