import httpx

with httpx.stream("POST", "http://127.0.0.1:8765/api/voice-command", json={"text": "gold prices today in India"}, timeout=60.0) as r:
    for line in r.iter_lines():
        print(line)
