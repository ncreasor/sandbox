import uuid
from openai import AsyncOpenAI
import base64
import requests, asyncio
from functools import partial
from logic.cache import get_cache_config

async def run_blocking(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

async def acs(config, pyrus_key):
    def get_token():
        return requests.post(
            "https://api.pyrus.com/v4/auth",
            json={"login": config["config"]["bot_login"], "security_key": pyrus_key},
            timeout=10
        ).json().get("access_token")
    return await run_blocking(get_token)

async def inf(url, name, pyrus_key):
    config = get_cache_config(pyrus_key)
    token = await acs(config, pyrus_key)
    client = AsyncOpenAI(api_key=config["api_keys"]["openai_api_key"])

    def download():
        return requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20).content

    ext = ".jpg" if name.endswith(".jpg") else ".ogg" if name.endswith(".ogg") else None
    if not ext: return None

    path = f"/tmp/file_{uuid.uuid4().hex}{ext}"
    with open(path, "wb") as f:
        f.write(await run_blocking(download))

    text = await (extract(path, client) if ext == ".jpg" else transcript(path, client))
    return text


async def extract(path, client):
    try:
        with open(path, "rb") as img:
            img_b64 = base64.b64encode(img.read()).decode()
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "Отвечай только на русском языке. Кратко и по делу."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Ты работаешь в паре с ботом техподдержки. Твоя задача — описать поступившую фотографию. "
                                    "Извлеки полезную информацию с фотографии и опиши её для последующей обработки. "
                                    "Если это ошибка — опиши только её. Если это таблица или отчёт — выпиши главное. "
                                    "Игнорируй интерфейсы и лишние элементы программы. Ответ должен быть в пределах пары предложений."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                            }
                        ]
                    }
                ],
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        print("Extraction error:", e)
        return ""


async def transcript(path, client):
    try:
        with open(path, "rb") as f:
            resp = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
            return resp.text.strip()
    except Exception as e:
        print("Transcription error:", e)
        return ""
