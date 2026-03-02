import os
import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

def test_api():
    if not API_KEY:
        print("Error: TWELVE_DATA_API_KEY not set in environment.")
        return
    url = f"https://api.twelvedata.com/quote?symbol=BTC/USD,XAU/USD&apikey={API_KEY}"
    print(f"Fetching: {url}")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        print(resp.json())

if __name__ == "__main__":
    test_api()
