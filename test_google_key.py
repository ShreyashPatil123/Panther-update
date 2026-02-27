
import asyncio
import httpx
import os
from dotenv import load_dotenv

async def test_google_key():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    # Using Gemini API via OpenAI-compatible endpoint as used in the app if applicable,
    # or just standard Gemini API.
    # The app uses: https://generativelanguage.googleapis.com/v1beta/openai
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": "hi"}]}]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            print(f"Status: {response.status_code}")
            # print(f"Response: {response.text}")
            if response.status_code == 200:
                print("Google API Key works!")
            else:
                print(f"Google API Key failed: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_google_key())
