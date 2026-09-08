import os
import io
import requests
from faster_whisper import WhisperModel as whisper
import asyncio
from celery import Celery
from celery.utils.log import get_task_logger
from vkbottle import API
from vkbottle.http import AiohttpClient
from vkbottle import DocMessagesUploader
from dotenv import load_dotenv
import time
from promts import get_whisper_prompt
import redis

r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
result = {}

load_dotenv() # загружаем переменные окружения из .env

app = Celery('tasks', broker='redis://127.0.0.1:6379/0', backend='redis://127.0.0.1:6379/0')
logger = get_task_logger(__name__)

model = whisper("medium", device="cpu", compute_type="int8") # инициализация модели

@app.task(bind=True)
def transcribe_vk_audio_task(self, audio_url, peer_id, doc_id=None):
    # 1. Если есть doc_id, получаем ссылку
    start_time = time.time()
    if doc_id:
        async def refresh_link():
            async with AiohttpClient() as http_client:
                local_api = API(token=os.getenv("VK_TOKEN"), http_client=http_client)
                try:
                    # Запрашиваем инфо о документе
                    docs = await local_api.docs.get_by_id(docs=doc_id)
                    if docs:
                        return docs[0].url
                except Exception as e:
                    logger.error(f"Не удалось обновить ссылку через API: {e}")
                return audio_url

        audio_url = asyncio.run(refresh_link())

    # 2. Определяем расширение более жестко
    is_video = any(x in audio_url.lower() for x in ["mp4", "video", "mov", "mpeg", "doc"])
    ext = "mp4" if is_video else "ogg"
    
    local_filename = f"downloads/file_{self.request.id}.{ext}"
    
    try:
        # Максимально полные заголовки для обхода защиты ВК
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://vk.com/',
            'Origin': 'https://vk.com/',
            'Connection': 'keep-alive',
        }
        
        # Скачивание
        with requests.get(audio_url, stream=True, headers=headers, timeout=60) as response:
            response.raise_for_status()
            
            # Проверяем реальный тип контента
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                logger.error(f"ВК все еще требует авторизацию. Тип: {content_type}")
                # Если это видео, попробуем другой URL
                raise ValueError("ВК заблокировал прямой доступ. Попробуй отправить файл без сжатия.")

            with open(local_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024): # качаем по 1МБ
                    f.write(chunk)
        
        file_size = os.path.getsize(local_filename)
        logger.info(f"Файл скачан: {local_filename}, размер: {file_size} байт")
        
        if file_size < 1000:
            raise ValueError("Файл слишком мал, возможно скачалась страница ошибки")
        
        # Важно: промт должен быть на том же языке, что и аудио
        current_prompt = get_whisper_prompt()
        logger.info(f"Запуск транскрибации для {peer_id} с промтом: {current_prompt}")
        # Транскрибация
        logger.info(f"Обработка для {peer_id}...")
        
        # записываем результат работы Whisper в переменную result
        segments, info = model.transcribe(
        local_filename, 
        beam_size=5, 
        initial_prompt=get_whisper_prompt(),
        language="ru"
        )

        formatted_lines = []
        for segment in segments:
            start = int(segment.start)
            minutes = start // 60
            seconds = start % 60
            timestamp = f"[{minutes:02d}:{seconds:02d}]"
    
            text_line = f"{timestamp} {segment.text.strip()}"
            formatted_lines.append(text_line)

        # Собираем всё в одно сообщение
        text = "\n".join(formatted_lines) if formatted_lines else "[Речь не распознана]"

        # Асинхронная отправка
        async def send_msg():
            async with AiohttpClient() as http_client:
                local_api = API(token=os.getenv("VK_TOKEN"), http_client=http_client)
                
                # Если аудио длится более 600 секунд (10 минут)
                if info.duration > 600:
                    # Создаем текстовый файл в памяти
                    file_stream = io.BytesIO(text.encode('utf-8'))
                    file_stream.name = "transcript.txt"
                    
                    uploader = DocMessagesUploader(local_api)
                    doc = await uploader.upload(
                        title=f"Расшифровка_{int(info.duration)}сек.txt",
                        file_source=file_stream,
                        peer_id=peer_id
                    )
                    await local_api.messages.send(
                        peer_id=peer_id, 
                        message="📝 Запись длинная, подготовил для тебя файл:", 
                        attachment=doc, 
                        random_id=0
                    )
                else:
                    # Обычная отправка текстом для коротких аудио
                    await local_api.messages.send(
                        peer_id=peer_id, 
                        message=f"📝 Результат расшифровки:\n\n{text}", 
                        random_id=0
                    )

        asyncio.run(send_msg())

    except Exception as e: # любая ошибка при скачивании, транскрибации или отправке будет обработана здесь
        logger.error(f"Ошибка: {e}")
        async def send_err():
            async with AiohttpClient() as http_client:
                local_api = API(token=os.getenv("VK_TOKEN"), http_client=http_client)
                await local_api.messages.send(peer_id=peer_id, message="❌ Ошибка обработки.", random_id=0)
        
        asyncio.run(send_err()) # отправляем сообщение об ошибке
    finally:
        r.decr("dionis_active_tasks")
        logger.info(f"Задача для {peer_id} завершена. Активных задач: {r.get('dionis_active_tasks')}")

        if os.path.exists(local_filename):
            os.remove(local_filename)  # удаляем файл после обработки
    end_time = time.time()
    
    logger.info(f"Время обработки: {end_time - start_time:.2f} секунд")
