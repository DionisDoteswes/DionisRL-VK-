# vk_bot.py -  Основной файл бота для ВКонтакте, который обрабатывает сообщения и отправляет задачи на транскрипцию в Celery.
import os
from vkbottle.bot import Bot, Message
from tasks_vk import transcribe_vk_audio_task # Импортируем задачу
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("VK_TOKEN")
if not TOKEN:
    exit("Ошибка: VK_TOKEN не найден в переменных окружения!")

bot = Bot(token=TOKEN)

@bot.on.message()
async def audio_handler(message: Message):
    audio_url = None
    
    # 1. Сначала ищем вложения в самом сообщении
    attachments = message.attachments or []
    
    # 2. Если вложений нет, проверяем пересланные сообщения (fwd_messages)
    if not attachments and message.fwd_messages:
        # Берем вложения из первого пересланного сообщения
        attachments = message.fwd_messages[0].attachments
    
    # 3. Если и там нет, проверяем "ответ" на сообщение (reply_message)
    if not attachments and message.reply_message:
        attachments = message.reply_message.attachments

    # Теперь ищем аудио в списке вложений
    for attachment in attachments:
        if attachment.audio_message:
            audio_url = attachment.audio_message.link_ogg
            break
        elif attachment.audio and hasattr(attachment.audio, 'url'):
            audio_url = attachment.audio.url
            break
        elif attachment.doc and attachment.doc.ext == "mp3":
            audio_url = attachment.doc.url
            break

    if audio_url:
        await message.answer("🎙 Нашел аудио. Начинаю расшифровку...")
        transcribe_vk_audio_task.delay(audio_url, message.peer_id)
    else:
        # Оставляем реакцию на обычный текст, чтобы понимать, что бот жив
        if message.text.lower() in ["привет", "начать"]:
            await message.answer("Привет! Отправь мне голосовое сообщение (можно пересланное), и я его расшифрую.")

if __name__ == "__main__":
    bot.run_forever()
    
