import anthropic
import base64
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="invoicebot/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

with open("kakran_invoice.jpg", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data,
                },
            },
            {
                "type": "text",
                "text": "Is invoice se nikalo JSON mein: invoice_no, date, gst_no, lorry_no, amount, grand_total. Sirf JSON return karo."
            }
        ],
    }]
)

print(response.content[0].text)