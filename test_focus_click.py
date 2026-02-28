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
        
        print("Wait 3 seconds...")
        await asyncio.sleep(3)
        
        page = await context.new_page()
        await page.goto("about:blank")
        print("Bringing to front...")
        await page.bring_to_front()
        
        # KEY FIX: Click the page so the OS gives the tab foreground focus!
        print("Clicking body to steal OS focus...")
        await page.click("body", force=True)
        await asyncio.sleep(0.5)
        
        print("Typing via pyautogui...")
        await asyncio.to_thread(type_url, "https://www.wikipedia.org")
        
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except:
            pass
        print("Final URL:", page.url)

asyncio.run(main())
