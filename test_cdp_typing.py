import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        if not contexts:
            context = await browser.new_context()
        else:
            context = contexts[0]
            
        page = await context.new_page()
        await page.bring_to_front()
        print("Pressing Ctrl+L")
        await page.keyboard.press("Control+L")
        await asyncio.sleep(0.5)
        print("Typing URL")
        await page.keyboard.type("https://www.youtube.com", delay=50)
        print("Pressing Enter")
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)
        print("Current URL:", page.url)

asyncio.run(main())
