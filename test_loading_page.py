import asyncio
from playwright.async_api import async_playwright
import base64

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        url = "https://www.youtube.com"
        html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ background: #0f172a; color: #38bdf8; font-family: 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .box {{ background: #1e293b; padding: 24px 40px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); font-size: 28px; display: flex; align-items: center; gap: 16px; width: 70%; max-width: 800px; }}
        .icon {{ opacity: 0.7; font-size: 32px; }}
        .text {{ border-right: 3px solid #38bdf8; white-space: nowrap; overflow: hidden; animation: blink 0.75s step-end infinite; }}
        @keyframes blink {{ 50% {{ border-color: transparent; }} }}
    </style>
</head>
<body>
    <div class="box">
        <span class="icon">🌐</span>
        <span class="text" id="typewriter"></span>
    </div>
    <script>
        const targetUrl = "{url}";
        const element = document.getElementById("typewriter");
        let i = 0;
        function typeWriter() {{
            if (i < targetUrl.length) {{
                element.innerHTML += targetUrl.charAt(i);
                i++;
                setTimeout(typeWriter, Math.random() * 30 + 30);
            }} else {{
                setTimeout(() => {{ window.location.href = targetUrl; }}, 400);
            }}
        }}
        setTimeout(typeWriter, 300);
    </script>
</body>
</html>"""
        b64_html = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        data_url = f"data:text/html;base64,{b64_html}"
        
        await page.goto(data_url)
        print("Waiting for final URL to load...")
        try:
            await page.wait_for_url(f"*{url.replace('https://', '').replace('http://', '').strip('/')}*")
        except:
             # Just wait a bit if matching fails
             await asyncio.sleep(3)
        print("Final URL loaded!", page.url)
        await browser.close()

asyncio.run(main())
