import os
import requests
import whisper
import asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from vkbottle import API
from vkbottle.http import AiohttpClient
from dotenv import load_dotenv

load_dotenv() # загружаем переменные окружения из .env

app = Celery('tasks', broker='redis://127.0.0.1:6379/0', backend='redis://127.0.0.1:6379/0')
logger = get_task_logger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium") # можно указать другую модель, например "tiny", "medium" и т.д.
model = whisper.load_model(WHISPER_MODEL) # загружаем модель один раз при инициализации задачи, чтобы не делать это при каждом вызове задачи

@app.task(bind=True)
def transcribe_vk_audio_task(self, audio_url, peer_id):
    local_filename = f"downloads/audio_{self.request.id}.ogg"
    
    try:
        # 1. Скачивание аудио
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # 2. Транскрибация
        logger.info(f"Обработка для {peer_id}...")
        result = model.transcribe(local_filename, language="ru")
        text = result.get("text", "[Речь не распознана]").strip()

        # 3. Асинхронная отправка
        async def send_msg(m_text):
            # Используем AiohttpClient для асинхронного взаимодействия с VK API
            async with AiohttpClient() as http_client:
                local_api = API(token=os.getenv("VK_TOKEN"), http_client=http_client)
                await local_api.messages.send(peer_id=peer_id, message=m_text, random_id=0)
        asyncio.run(send_msg(f"📝 Результат расшифровки:\n\n{text}"))

    except Exception as e: # любая ошибка при скачивании, транскрибации или отправке будет обработана здесь
        logger.error(f"Ошибка: {e}")
        async def send_err():
            async with AiohttpClient() as http_client:
                local_api = API(token=os.getenv("VK_TOKEN"), http_client=http_client)
                await local_api.messages.send(peer_id=peer_id, message="❌ Ошибка обработки.", random_id=0)
        
        asyncio.run(send_err())
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)  # удаляем файл после обработки