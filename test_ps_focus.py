import asyncio
from playwright.async_api import async_playwright
import time
import subprocess
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        
        print("Wait 2 seconds...")
        await asyncio.sleep(2)
        
        page = await context.new_page()
        # Set a very unique title
        await page.evaluate('document.title = "PANTHER_TARGET_TAB"')
        await asyncio.sleep(1) # wait for title to set
        
        print("Stealing focus via PowerShell AppActivate...")
        ps_script = """
        $wshell = New-Object -ComObject wscript.shell;
        $success = $wshell.AppActivate('PANTHER_TARGET_TAB');
        Start-Sleep -Milliseconds 500;
        if ($success) {
            $wshell.SendKeys('^l');
            Start-Sleep -Milliseconds 100;
            $wshell.SendKeys('https://youtube.com{ENTER}');
        }
        """
        
        # We run the powershell script
        with open("focus.ps1", "w") as f:
            f.write(ps_script)
            
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "focus.ps1"])
        
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except:
            pass
        print("Final URL:", page.url)

asyncio.run(main())
