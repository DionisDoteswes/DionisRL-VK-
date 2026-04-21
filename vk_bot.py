# vk_bot.py -  Основной файл бота для ВКонтакте, который обрабатывает сообщения и отправляет задачи на транскрипцию в Celery.
import os
from vkbottle.bot import Bot, Message
from tasks_vk import transcribe_vk_audio_task # Импортируем задачу
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("VK_TOKEN") # Получаем токен из переменных окружения
if not TOKEN:
    exit("Ошибка: VK_TOKEN не найден в переменных окружения!")

bot = Bot(token=TOKEN)

# Добавление новых слов
@bot.on.message(text="/промпт <words>")
async def add_prompts_handler(message: Message, words: str):
    try:
        # Добавляем запятую перед новым словом для корректного разделения
        with open("promts.txt", "a", encoding="utf-8") as f:
            f.write(f", {words}")
        await message.answer(f"✅ Новые термины добавлены.\nТекущий список можно посмотреть через /слова")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

#Просмотр текущих слов
@bot.on.message(text="/слова")
async def show_prompts_handler(message: Message):
    try:
        if os.path.exists("promts.txt"):
            with open("promts.txt", "r", encoding="utf-8") as f:
                content = f.read().strip()
            await message.answer(f"📝 Текущие промпты:\n\n{content if content else 'Список пуст'}")
        else:
            await message.answer("📁 Файл promts.txt еще не создан.")
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения: {e}")

# Полная очистка файла
@bot.on.message(text="/очистить")
async def clear_prompts_handler(message: Message):
    try:
        with open("promts.txt", "w", encoding="utf-8") as f:
            f.write("") # Перезаписываем пустой строкой
        await message.answer("🗑 Список промптов полностью очищен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка очистки: {e}")

@bot.on.message()
async def audio_handler(message: Message):
    audio_url = None
    
    # Сначала ищем вложения в самом сообщении
    attachments = message.attachments or []
    
    # Если вложений нет, проверяем пересланные сообщения (fwd_messages)
    if not attachments and message.fwd_messages:
        # Берем вложения из первого пересланного сообщения
        attachments = message.fwd_messages[0].attachments
    
    # Если и там нет, проверяем "ответ" на сообщение (reply_message)
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
    
