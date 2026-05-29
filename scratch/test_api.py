import urllib.request
import urllib.error
import json

test_cases = [
    {"message": "rekomendasi kuliner di imy", "session_token": "token-1"},
    {"message": "rekomendasi kuliner di kota udang", "session_token": "token-2"},
    {"message": "bantu saya membuatkan rencana liburan ke majalengka untuk 10 orang dengan budget 500k dalam 2 hari", "session_token": "token-3"}
]

for tc in test_cases:
    req = urllib.request.Request(
        'http://localhost:8001/api/v1/chatbot/ask',
        data=json.dumps(tc).encode(),
        headers={'Content-Type': 'application/json'}
    )
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode())
        print(f"\nUser: {tc['message']}")
        print(f"Wilayah Terdeteksi: {data['data'].get('wilayah_terdeteksi')}")
        print(f"Answer: {data['data']['answer'][:100]}...")
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}")
