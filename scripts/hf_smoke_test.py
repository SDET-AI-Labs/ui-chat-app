import asyncio
from chatstack.settings import settings
from chatstack.models.hf_infer import HFBackend
from huggingface_hub.errors import HfHubHTTPError

async def try_model(model_id: str):
    print(f"\n[SMOKE] Trying model: {model_id}")
    b = HFBackend(settings.hf_api_base, settings.hf_api_key, model_id)
    try:
        out = await b.complete([
            {"role": "user", "content": "give 2 short testing strategies"}
        ])
        print("[OK] Response:\n" + out)
        return True
    except HfHubHTTPError as he:
        print(f"[FAIL] HfHubHTTPError: {he}")
        return False
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        return False

async def main():
    candidates = [
        settings.hf_model,
        # A few common serverless-capable instruct models
        "HuggingFaceH4/zephyr-7b-beta",
        "tiiuae/falcon-7b-instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "google/gemma-2-2b-it",
    ]

    for mid in candidates:
        ok = await try_model(mid)
        if ok:
            print(f"\n[SMOKE] Success with model: {mid}")
            return
    print("\n[SMOKE] All candidates failed.")

if __name__ == "__main__":
    asyncio.run(main())
