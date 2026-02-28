import ctypes
import time

def force_focus_by_title(title_substring):
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    
    # Alt key trick
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002

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
        # Simulate pressing Alt
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
        
        # Bring to front
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
        
        # Release Alt
        ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        return True
    return False

if __name__ == "__main__":
    import sys
    print("Found and focused:", force_focus_by_title(sys.argv[1] if len(sys.argv) > 1 else "Chrome"))
