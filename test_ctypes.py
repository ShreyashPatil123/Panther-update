import asyncio
from playwright.async_api import async_playwright
import time
import ctypes

def type_address_bar_ctypes(url: str):
    # Virtual key codes
    VK_CONTROL = 0x11
    VK_L = 0x4C
    VK_RETURN = 0x0D
    KEYEVENTF_KEYUP = 0x0002

    # Press Ctrl+L
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_L, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_L, 0, KEYEVENTF_KEYUP, 0)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.2)
    
    # Type URL
    for char in url:
        vk = ctypes.windll.user32.VkKeyScanW(ord(char))
        shift = (vk & 0x0100) != 0
        vk_code = vk & 0xFF
        
        if shift:
            ctypes.windll.user32.keybd_event(0x10, 0, 0, 0) # Shift down
            
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        
        if shift:
            ctypes.windll.user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0) # Shift up
            
        time.sleep(0.03)
        
    # Press Enter
    time.sleep(0.1)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        page = await context.new_page()
        await page.bring_to_front()
        await asyncio.sleep(1.0)
        
        print("Typing via ctypes...")
        await asyncio.to_thread(type_address_bar_ctypes, "https://www.youtube.com")
        
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except:
            pass
        print("Final URL:", page.url)

asyncio.run(main())
