import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("NVIDIA_API_KEY", "")

def get_all_models():
    try:
        resp = requests.get("http://127.0.0.1:8000/api/models")
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except Exception as e:
        print(f"Error fetching models: {e}")
    return []

def test_model(model_name: str, provider: str):
    if provider != "nvidia":
        return True, "Skipped (not NVIDIA)"
    
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Say 'hello' in one word."}],
        "max_tokens": 10
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return True, "OK"
        else:
            return False, f"HTTP {r.status_code} - {r.text[:100]}"
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    if not API_KEY:
        try:
            from src.core.config import get_settings
            API_KEY = get_settings().nvidia_api_key
        except Exception:
            pass

    if not API_KEY or API_KEY == "your_api_key_here":
        print("Missing NVIDIA_API_KEY. Cannot test NVIDIA models.")
        exit(1)

    print("Fetching frontend models list...")
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from src.api.nvidia_client import NVIDIAClient
    
    # Bypass init error
    client = NVIDIAClient(api_key=API_KEY)
    frontend_models = client.get_available_models()
    nvidia_models = [{"id": m, "provider": "nvidia"} for m in frontend_models]

    print(f"Total frontend models to test: {len(nvidia_models)}")
    
    print("--- Start Testing ---")
    failing_models = []
    
    count = 0
    for m in nvidia_models:
        m_id = m.get("id")
        count += 1
        print(f"Testing {count}/{len(nvidia_models)}: {m_id}...", end=" ", flush=True)
        ok, reason = test_model(m_id, "nvidia")
        if ok:
            print("[\033[92mPASS\033[0m]")
        else:
            print(f"[\033[91mFAIL\033[0m] -> {reason}")
            failing_models.append((m_id, reason))
        time.sleep(0.1) # tiny throttle
        
    print("\n\n--- RESULTS ---")
    print(f"Total Tested: {len(nvidia_models)}")
    print(f"Working: {len(nvidia_models) - len(failing_models)}")
    print(f"Failing: {len(failing_models)}")
    
    if failing_models:
        print("\nList of Failing Models:")
        for name, reason in failing_models:
            print(f"- {name} (Error: {reason})")
    
    # Write report
    with open("failing_models.json", "w") as f:
        json.dump(failing_models, f, indent=2)
