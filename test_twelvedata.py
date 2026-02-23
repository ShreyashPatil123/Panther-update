import httpx

API_KEY = "b4eff512ca714420ae7a62baf9333d70"

def test_api():
    url = f"https://api.twelvedata.com/quote?symbol=BTC/USD,XAU/USD&apikey={API_KEY}"
    print(f"Fetching: {url}")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        print(resp.json())

if __name__ == "__main__":
    test_api()
