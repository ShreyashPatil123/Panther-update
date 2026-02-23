import httpx, json

queries = [
    "What is the current stock price of Apple?",
    "Gold prices today in India",
    "Bitcoin price right now",
]

for q in queries:
    print(f"\n{'='*60}")
    print(f"QUERY: {q}")
    print('='*60)
    with httpx.stream("POST", "http://127.0.0.1:8765/api/voice-command",
                       json={"text": q}, timeout=60.0) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                    if "text" in d:
                        print(d["text"], end="")
                except:
                    pass
    print()
