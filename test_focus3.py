import asyncio
from playwright.async_api import async_playwright
import ctypes
import time

def force_focus():
    import win32gui
    import win32con
    import win32com.client
    
    # We find the foreground window right now and see if it's our browser.
    # Actually, we can just find any window with "PANTHER_TARGET" in the title.
    hwnd = win32gui.FindWindow(None, None)
    target_hwnd = None
    
    def enum_cb(h, _):
        nonlocal target_hwnd
        if win32gui.IsWindowVisible(h):
            title = win32gui.GetWindowText(h)
            if "PANTHER_TARGET" in title:
                target_hwnd = h
    win32gui.EnumWindows(enum_cb, None)
    
    if target_hwnd:
        # The WScript.Shell SendKeys('%') hack to bypass ForegroundLockTimeout
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys('%')  # Send Alt key
        
        # Now set foreground
        win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(target_hwnd)
        return True
    return False

def type_url(url: str):
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
    time.sleep(0.5) 
    
    for char in url:
        vk = ctypes.windll.user32.VkKeyScanW(ord(char))
        shift = (vk & 0x0100) != 0
        vk_code = vk & 0xFF
        
        if shift: ctypes.windll.user32.keybd_event(0x10, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        if shift: ctypes.windll.user32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)
        
    time.sleep(0.1)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        
        await asyncio.sleep(2)
        page = await context.new_page()
        await page.bring_to_front()
        
        # Set recognizable title
        await page.evaluate('document.title = "PANTHER_TARGET_TAB"')
        await asyncio.sleep(0.5) # Wait for title to update in OS
        
        # Attempt to force focus
        success = await asyncio.to_thread(force_focus)
        print("Forced focus:", success)
        await asyncio.sleep(0.2)
        
        # Type
        await asyncio.to_thread(type_url, "https://example.com")
        
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except: pass
        print("Final URL:", page.url)

asyncio.run(main())
