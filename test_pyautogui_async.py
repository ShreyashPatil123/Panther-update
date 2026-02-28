import asyncio
from playwright.async_api import async_playwright
import pyautogui
import time

def type_url(url):
    pyautogui.hotkey('ctrl', 'l')
    time.sleep(0.1)
    pyautogui.typewrite(url, interval=0.03)
    pyautogui.press('enter')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
            
        page = await context.new_page()
        await page.bring_to_front()
        
        # Give OS time to focus window
        await asyncio.sleep(0.5)
        
        # Run typing in a thread so it doesn't block asyncio
        await asyncio.to_thread(type_url, "https://www.youtube.com")
        
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except:
            pass
        print("Final URL:", page.url)

asyncio.run(main())
