import asyncio
from src.capabilities.research import ResearchEngine, ResearchSource

async def main():
    e = ResearchEngine()
    source = ResearchSource(
        url="https://www.livepriceofgold.com/india-gold-price.html",
        title="Test",
        snippet="Test"
    )
    print("Fetching page content...")
    content = await e._fetch_page_content(source)
    with open("output2.txt", "w", encoding="utf-8") as f:
        f.write(f"--- EXTRACTED CONTENT (length: {len(content)}) ---\n")
        f.write(content + "\n")
        f.write("---------------------------------------------------\n")
    await e.close()

if __name__ == "__main__":
    asyncio.run(main())
