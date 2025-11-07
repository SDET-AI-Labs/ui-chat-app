import asyncio
from chatstack.models.openai_like import OpenAILikeBackend
from chatstack.settings import settings

async def main():
    b = OpenAILikeBackend(settings.openai_api_base, settings.openai_api_key, settings.openai_model, verify_ssl=settings.openai_verify_ssl)
    resp = await b.complete([{"role":"user","content":"Give me 3 test ideas"}])
    print(resp)

if __name__ == "__main__":
    asyncio.run(main())
