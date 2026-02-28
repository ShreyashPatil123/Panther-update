import asyncio
from playwright.async_api import async_playwright
import time
import ctypes

# Constants for Windows API
SW_RESTORE = 9
## Enumerating windows
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible

def force_foreground_by_title(title_substring):
    hwnds = []
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            if title_substring in buff.value:
                hwnds.append(hwnd)
        return True
    
    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    if hwnds:
        hwnd = hwnds[0]
        # AttachThreadInput trick to bypass Windows foreground lock
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(current_thread, target_thread, True)
        
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        
        user32.AttachThreadInput(current_thread, target_thread, False)
        return True
    return False

def type_address_bar_ctypes(url: str):
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
        
        print("Wait 3 seconds...")
        await asyncio.sleep(3)
        
        page = await context.new_page()
        # Set a unique title
        unique_title = "PANTHER_AUTOMATION_TARGET"
        await page.evaluate(f'document.title = "{unique_title}"')
        await page.bring_to_front()
        await asyncio.sleep(0.5)
        
        print("Stealing focus...")
        success = await asyncio.to_thread(force_foreground_by_title, unique_title)
        print("Focus stolen:", success)
        await asyncio.sleep(0.5)
        
        print("Typing via ctypes...")
        await asyncio.to_thread(type_address_bar_ctypes, "https://www.wikipedia.org")

        try:
            await page.wait_for_load_state("load", timeout=5000)
        except:
            pass
        print("Final URL:", page.url)

asyncio.run(main())
