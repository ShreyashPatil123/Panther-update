import httpx

q = "Gold prices today in India"
print(f"QUERY: {q}")
print()

with httpx.stream("POST", "http://127.0.0.1:8765/api/voice-command",
                   json={"text": q}, timeout=60.0) as r:
    for line in r.iter_lines():
        print(line)
