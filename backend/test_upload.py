import requests
import json
import base64

API_BASE = "http://127.0.0.1:8000"

# 1. Login to get token (create fake user or bypass auth for testing... Ah, we don't have token)
# Wait, auth locally usually requires firebase. Let's create a test endpoint in main.py to bypass auth temporarily if needed.

# Let's see if we can just test the financial extractor directly first.
from app.financial_extractor import extract_financial_data

try:
    with open("test_hausgeld.pdf", "rb") as f:
        from app.pdf_ingest import extract_text_from_pdf_bytes
        text = extract_text_from_pdf_bytes(f.read())
        print(f"Extracted {len(text)} chars from PDF.")
        
        data = extract_financial_data(text)
        print(json.dumps(data.model_dump(), indent=2))
except Exception as e:
    import traceback
    traceback.print_exc()

