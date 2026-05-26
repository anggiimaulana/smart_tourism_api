import sys
from app.services.intent_classifier import classify_intent, _normalize_text

test_cases = [
    "di jatibarang",
    "kalo di cirebon ada apa aja?",
    "sepeda warna biru",
    "aku ganteng gak",
    "di jepang"
]

for msg in test_cases:
    res = classify_intent(msg)
    print(f"User: {msg}")
    print(f"Intent: {res['intent']} (has_tourism: {res['has_tourism_intent']})")
    print("-" * 40)
