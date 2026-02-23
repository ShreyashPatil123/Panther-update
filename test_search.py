import asyncio
from src.capabilities.research import ResearchEngine

async def main():
    e = ResearchEngine()
    print("Searching...")
    results = await e._search_ddg("gold price 24 carat per gram india today", 5)
    for r in results:
        print(f"TITLE: {r.title}")
        print(f"URL: {r.url}")
        print(f"SNIPPET: {r.snippet[:200]}...")
        # print(f"CONTENT: {r.content[:200]}..." if r.content else "CONTENT: None")
        print("-" * 40)
    await e.close()

if __name__ == "__main__":
    asyncio.run(main())
