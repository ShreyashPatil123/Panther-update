import asyncio
from playwright.async_api import async_playwright
import pyautogui
import time

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        if not contexts:
            context = await browser.new_context()
        else:
            context = contexts[0]
            
        page = await context.new_page()
        # Bring page to front via JavaScript to ensure OS focus if possible
        await page.bring_to_front()
        await page.evaluate("window.focus()")
        time.sleep(1) # Wait for focus
        
        # Press Ctrl+L to focus address bar
        pyautogui.hotkey('ctrl', 'l')
        time.sleep(0.5)
        
        # Type URL with a delay to simulate human typing
        pyautogui.typewrite('https://www.youtube.com/', interval=0.08)
        pyautogui.press('enter')
        
        await asyncio.sleep(4)
        print("Final URL:", page.url)

asyncio.run(main())
