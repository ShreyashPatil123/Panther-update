"""Discover ALL models from NVIDIA NIM API and test chat-compatible ones."""
import asyncio
import httpx
import json
import time

API_KEY = "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"
BASE_URL = "https://integrate.api.nvidia.com/v1"


async def discover_models(client: httpx.AsyncClient) -> list:
    """Fetch all models from the /models endpoint."""
    print("Fetching model list from NVIDIA API...")
    try:
        response = await client.get(f"{BASE_URL}/models", timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            print(f"Found {len(models)} total models from API\n")
            return models
        else:
            print(f"Failed to list models: HTTP {response.status_code}")
            print(response.text[:500])
            return []
    except Exception as e:
        print(f"Error listing models: {e}")
        return []


async def test_model(client: httpx.AsyncClient, model_id: str) -> dict:
    """Test a single model with a short chat prompt."""
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Say hi in one word."}],
        "max_tokens": 20,
        "temperature": 0.5,
        "stream": False,
    }

    start = time.monotonic()
    try:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=60.0,
        )
        latency = round((time.monotonic() - start) * 1000)

        if response.status_code == 200:
            data = response.json()
            content = ""
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"].get("content", "") or ""
            preview = content.strip()[:50].replace("\n", " ")
            return {"model": model_id, "status": "OK", "code": 200, "latency_ms": latency, "response": preview}
        else:
            detail = ""
            try:
                body = response.json()
                detail = body.get("detail", body.get("title", response.text[:100]))
            except Exception:
                detail = response.text[:100]
            return {"model": model_id, "status": f"HTTP {response.status_code}", "code": response.status_code, "latency_ms": latency, "response": str(detail)[:80]}

    except httpx.TimeoutException:
        latency = round((time.monotonic() - start) * 1000)
        return {"model": model_id, "status": "TIMEOUT", "code": 0, "latency_ms": latency, "response": "Timed out"}
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000)
        return {"model": model_id, "status": "ERROR", "code": 0, "latency_ms": latency, "response": str(e)[:80]}


async def main():
    print("=" * 100)
    print("NVIDIA NIM — Full Model Discovery & Testing")
    print("=" * 100)

    client = httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )

    # Step 1: Discover all models
    all_models = await discover_models(client)

    if not all_models:
        print("No models found. Exiting.")
        await client.aclose()
        return

    # Categorize models
    chat_models = []
    other_models = []

    for m in all_models:
        model_id = m.get("id", "")
        # Filter for chat/completion models — skip embedding, reranking, 
        # image, audio, vlm (vision-language) models that don't support /chat/completions
        model_type = m.get("object", "")
        
        # We'll test ALL models against chat/completions and see which work
        chat_models.append(model_id)

    chat_models.sort()
    print(f"Will test {len(chat_models)} models against /chat/completions endpoint\n")

    # Step 2: Test all models
    working = []
    failed = []
    
    # Test in batches of 5 for speed (with semaphore to avoid rate limiting)
    sem = asyncio.Semaphore(3)
    
    async def test_with_sem(model_id, index):
        async with sem:
            return await test_model(client, model_id), index

    tasks = [test_with_sem(m, i) for i, m in enumerate(chat_models)]
    
    total = len(chat_models)
    results_list = [None] * total
    
    for coro in asyncio.as_completed(tasks):
        result, idx = await coro
        results_list[idx] = result
        done_count = sum(1 for r in results_list if r is not None)
        status_icon = "✅" if result["status"] == "OK" else "❌"
        print(f"[{done_count:3d}/{total}] {status_icon} {result['model']}: {result['status']} ({result['latency_ms']}ms) — {result['response']}")
        
        if result["status"] == "OK":
            working.append(result)
        else:
            failed.append(result)

    await client.aclose()

    # Sort results
    working.sort(key=lambda r: r["model"])
    failed.sort(key=lambda r: r["model"])

    # Summary
    print("\n" + "=" * 100)
    print(f"RESULTS: {len(working)}/{total} models work with /chat/completions")
    print("=" * 100)

    print(f"\n✅ WORKING CHAT MODELS ({len(working)}):")
    for r in working:
        print(f"   • {r['model']} ({r['latency_ms']}ms)")

    print(f"\n❌ FAILED MODELS ({len(failed)}):")
    # Group failures by error type
    by_code = {}
    for r in failed:
        code = r["code"]
        by_code.setdefault(code, []).append(r)
    for code, items in sorted(by_code.items()):
        print(f"\n   HTTP {code} ({len(items)} models):")
        for r in items:
            print(f"      • {r['model']}: {r['response']}")

    # Output copy-paste ready list
    print("\n" + "=" * 100)
    print("COPY-PASTE READY PYTHON LIST:")
    print("=" * 100)
    print("        return [")
    for r in working:
        print(f'            "{r["model"]}",')
    print("        ]")

    # Also write to a file for easy access
    with open("model_test_results.json", "w") as f:
        json.dump({
            "total_discovered": total,
            "working_count": len(working),
            "failed_count": len(failed),
            "working_models": [r["model"] for r in working],
            "failed_models": [{"model": r["model"], "status": r["status"], "detail": r["response"]} for r in failed],
        }, f, indent=2)
    print("\nResults saved to model_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
