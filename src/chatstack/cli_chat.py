import asyncio
from .settings import settings
from .models import OpenAILikeBackend, OllamaBackend, ChatBackend

async def main():
    if settings.backend == "openai_like":
        backend = OpenAILikeBackend(settings.openai_api_base, settings.openai_api_key, settings.openai_model)
    else:
        backend = OllamaBackend(settings.ollama_base, settings.ollama_model)

    print(f"[ChatStack CLI] Backend={settings.backend}")
    messages = []
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        messages.append({"role":"user","content":user})
        reply = await backend.complete(messages)
        print(f"bot> {reply}")
        messages.append({"role":"assistant","content":reply})

if __name__ == "__main__":
    asyncio.run(main())
