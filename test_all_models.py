"""Discover and test ALL models from NVIDIA NIM, Ollama Cloud, and Google Gemini."""
import asyncio
import httpx
import json
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

# Fix Windows console encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# ── API Keys & URLs ───────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")


# ── Discovery ─────────────────────────────────────────────────────────────────

async def discover_nvidia(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(f"{NVIDIA_BASE_URL}/models", timeout=30.0)
    if resp.status_code != 200:
        print(f"  NVIDIA /models returned {resp.status_code}")
        return []
    return sorted(m["id"] for m in resp.json().get("data", []) if m.get("id"))


async def discover_ollama(client: httpx.AsyncClient) -> list[str]:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/models"
    resp = await client.get(url, timeout=30.0)
    if resp.status_code != 200:
        print(f"  Ollama /models returned {resp.status_code}")
        return []
    return sorted(m["id"] for m in resp.json().get("data", []) if m.get("id"))


async def discover_gemini(_client: httpx.AsyncClient) -> list[str]:
    # Use a fresh client without Bearer auth — Gemini discovery uses ?key= param
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": GOOGLE_API_KEY},
        )
    if resp.status_code != 200:
        print(f"  Gemini /models returned {resp.status_code}")
        return []
    models = []
    for m in resp.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            models.append(m["name"].replace("models/", ""))
    return sorted(models)


# ── Test a single model ───────────────────────────────────────────────────────

async def test_model(
    client: httpx.AsyncClient,
    model_id: str,
    base_url: str,
    provider: str,
) -> dict:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Say hi in one word."}],
        "max_tokens": 20,
        "temperature": 0.5,
        "stream": False,
    }

    start = time.monotonic()
    try:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Accept": "application/json"},
            timeout=60.0,
        )
        latency = round((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            content = ""
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "") or ""
            preview = content.strip()[:50].replace("\n", " ")
            return {
                "model": model_id, "provider": provider, "status": "OK",
                "code": 200, "latency_ms": latency, "response": preview,
            }
        else:
            detail = ""
            try:
                body = resp.json()
                detail = str(body.get("detail", body.get("error", body.get("title", resp.text[:100]))))
            except Exception:
                detail = resp.text[:100]
            return {
                "model": model_id, "provider": provider,
                "status": f"HTTP {resp.status_code}", "code": resp.status_code,
                "latency_ms": latency, "response": str(detail)[:80],
            }
    except httpx.TimeoutException:
        latency = round((time.monotonic() - start) * 1000)
        return {
            "model": model_id, "provider": provider, "status": "TIMEOUT",
            "code": 0, "latency_ms": latency, "response": "Timed out",
        }
    except Exception as e:
        latency = round((time.monotonic() - start) * 1000)
        return {
            "model": model_id, "provider": provider, "status": "ERROR",
            "code": 0, "latency_ms": latency, "response": str(e)[:80],
        }


# ── Test all models for a provider ────────────────────────────────────────────

async def test_provider(
    name: str,
    discover_fn,
    base_url: str,
    auth_headers: dict,
    sem_limit: int = 3,
) -> dict:
    client = httpx.AsyncClient(headers=auth_headers, timeout=60.0)
    try:
        models = await discover_fn(client)
        if not models:
            print(f"  No models found for {name}. Skipping.")
            return {"provider": name, "total": 0, "working": [], "failed": []}

        print(f"  Found {len(models)} models. Testing...\n")
        sem = asyncio.Semaphore(sem_limit)
        working, failed = [], []

        async def run(mid, idx):
            async with sem:
                return await test_model(client, mid, base_url, name), idx

        tasks = [run(m, i) for i, m in enumerate(models)]
        total = len(models)
        done = 0

        for coro in asyncio.as_completed(tasks):
            result, _ = await coro
            done += 1
            icon = "OK" if result["status"] == "OK" else "FAIL"
            print(
                f"  [{done:3d}/{total}] [{icon:4s}] {result['model']}: "
                f"{result['status']} ({result['latency_ms']}ms) -- {result['response']}"
            )
            (working if result["status"] == "OK" else failed).append(result)

        working.sort(key=lambda r: r["model"])
        failed.sort(key=lambda r: r["model"])
        return {"provider": name, "total": total, "working": working, "failed": failed}
    finally:
        await client.aclose()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 100)
    print("  PANTHER — Multi-Provider Model Discovery & Testing")
    print("=" * 100)

    results = {}

    # ── NVIDIA ────────────────────────────────────────────────────────────
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "your_api_key_here":
        print(f"\n{'='*100}\n  NVIDIA NIM\n{'='*100}")
        results["nvidia"] = await test_provider(
            "nvidia",
            discover_nvidia,
            NVIDIA_BASE_URL,
            {
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    else:
        print("\n  [SKIP] NVIDIA — no API key configured")

    # ── Ollama Cloud ──────────────────────────────────────────────────────
    if OLLAMA_API_KEY:
        print(f"\n{'='*100}\n  OLLAMA CLOUD\n{'='*100}")
        results["ollama"] = await test_provider(
            "ollama",
            discover_ollama,
            OLLAMA_BASE_URL.rstrip("/"),
            {
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    else:
        print("\n  [SKIP] Ollama — no API key configured")

    # ── Gemini ────────────────────────────────────────────────────────────
    if GOOGLE_API_KEY:
        print(f"\n{'='*100}\n  GOOGLE GEMINI\n{'='*100}")
        results["gemini"] = await test_provider(
            "gemini",
            discover_gemini,
            "https://generativelanguage.googleapis.com/v1beta/openai",
            {
                "Authorization": f"Bearer {GOOGLE_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    else:
        print("\n  [SKIP] Gemini — no API key configured")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  SUMMARY")
    print("=" * 100)

    for prov, data in results.items():
        w = len(data["working"])
        t = data["total"]
        f = len(data["failed"])
        print(f"\n  {prov.upper()}: {w}/{t} working, {f} failed")

        if data["working"]:
            print(f"\n    Working models ({w}):")
            for r in data["working"]:
                print(f"      {r['model']} ({r['latency_ms']}ms)")

        if data["failed"]:
            print(f"\n    Failed models ({f}):")
            for r in data["failed"]:
                print(f"      {r['model']}: {r['status']} -- {r['response']}")

    # ── Copy-paste ready lists ────────────────────────────────────────────
    for prov, data in results.items():
        if data["working"]:
            print(f"\n{'='*100}")
            print(f"  COPY-PASTE READY — {prov.upper()} WORKING MODELS:")
            print("=" * 100)
            print("        [")
            for r in data["working"]:
                print(f'            "{r["model"]}",')
            print("        ]")

    # ── Write JSON ────────────────────────────────────────────────────────
    output = {
        "test_date": datetime.now(timezone.utc).isoformat(),
    }
    for prov, data in results.items():
        output[prov] = {
            "total": data["total"],
            "working_count": len(data["working"]),
            "failed_count": len(data["failed"]),
            "working_models": [r["model"] for r in data["working"]],
            "failed_models": [
                {"model": r["model"], "status": r["status"], "detail": r["response"]}
                for r in data["failed"]
            ],
        }

    with open("all_model_test_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved to all_model_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
