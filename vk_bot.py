# vk_bot.py -  Основной файл бота для ВКонтакте, который обрабатывает сообщения и отправляет задачи на транскрипцию в Celery.
import os
from vkbottle.bot import Bot, Message
from vkbottle import DocMessagesUploader
from tasks_vk import transcribe_vk_audio_task # Импортируем задачу
from dotenv import load_dotenv
import zipfile
import logging
import redis
import threading
import time
import psutil

logging.basicConfig(level=logging.INFO)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
LIMIT = 5

load_dotenv()

TOKEN = os.getenv("VK_TOKEN") # Получаем токен из переменных окружения
if not TOKEN:
    exit("Ошибка: VK_TOKEN не найден в переменных окружения!")

bot = Bot(token=TOKEN)

MY_VK_ID = 123456789 
# Путь к логу MSI Afterburner
LOG_PATH = r"C:\Program Files (x86)\MSI Afterburner\HardwareMonitoring.hml"

def monitor_logic():
    logging.info("🛰 Фоновый мониторинг 'Ковчег' запущен.")
    while True:
        try:
            if os.path.exists(LOG_PATH):
                # Используем utf-8 с игнорированием ошибок
                with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    
                if len(lines) > 1:
                    last_line = lines[-1].split(",")
                    
                    if len(last_line) > 2:
                        try:
                            gpu_temp = float(last_line[2])
                            
                            # 1. Защита по перегреву GPU
                            if gpu_temp > 82:
                                bot.loop.create_task(
                                    bot.api.messages.send(
                                        peer_id=MY_VK_ID, 
                                        message=f"❗ КРИТИЧЕСКИЙ ПЕРЕГРЕВ ГП: {gpu_temp}°C! Выключаюсь...",
                                        random_id=0
                                    )
                                )
                                logging.error(f"Перегрев ГП! Температура: {gpu_temp}°C. Выключение.")
                                os.system("shutdown /s /t 10")
                                break
                                
                        except ValueError:
                            print("Ошибка преобразования температуры ГП")
            
            # 2. Мониторинг загрузки процессора (CPU) через psutil
            cpu_load = psutil.cpu_percent(interval=1)
            if cpu_load > 98:
                # Не выключаем ПК, а просто предупреждаем в личку, что Dionis работает на пределе
                bot.loop.create_task(
                    bot.api.messages.send(
                        peer_id=MY_VK_ID, 
                        message=f"⚠️ Процессор загружен на {cpu_load}%! Идет плотная обработка задач.",
                        random_id=0
                    )
                )
                
        except Exception as e:
            logging.error(f"Ошибка мониторинга: {e}")
        
        # Так как psutil внутри себя забирает 1 секунду на замер (interval=1),
        # пауза 59 секунд.
        time.sleep(59)

# Добавление новых слов
@bot.on.message(text="/промпт <words>")
async def add_prompts_handler(message: Message, words: str):
    try:
        with open("promts.txt", "a", encoding="utf-8") as f:
            f.write(f", {words}")
            logging.info(f"Добавлены новые термины: {words}")
        await message.answer(f"✅ Новые термины добавлены.\nТекущий список можно посмотреть через /слова")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {e}")

#Просмотр текущих слов
@bot.on.message(text="/слова")
async def show_prompts_handler(message: Message):
    try:
        if os.path.exists("promts.txt"):
            with open("promts.txt", "r", encoding="utf-8") as f:
                content = f.read().strip()
            await message.answer(f"📝 Текущие промпты:\n\n{content if content else 'Список пуст'}")
            logging.info("Показан текущий список промптов.")
        else:
            logging.warning("Файл promts.txt еще не создан.")
            await message.answer("📁 Файл promts.txt еще не создан.")
    except Exception as e:
        logging.error(f"Ошибка чтения: {e}")
        await message.answer(f"Ошибка чтения: {e}")

# Полная очистка файла
@bot.on.message(text="/очистить")
async def clear_prompts_handler(message: Message):
    try:
        with open("promts.txt", "w", encoding="utf-8") as f:
            f.write("")
        await message.answer("🗑 Список промптов полностью очищен.")
        logging.info("Список промптов полностью очищен.")
    except Exception as e:
        logging.error(f"Ошибка очистки: {e}")
        await message.answer(f"Ошибка очистки: {e}")

@bot.on.message(text="/репо")
async def send_repo_handler(message: Message):
    if message.from_id != 123456789:
        return

    zip_path = "dionis_source.zip"
    # Список файлов для архивации
    files = ["vk_bot.py", "tasks_vk.py", "promts.py", "requirements.txt", ".env"]
    
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                if os.path.exists(file):
                    zipf.write(file)
        
        # Загружаем файл в ВК
        uploader = DocMessagesUploader(bot.api)
        doc = await uploader.upload(
            title="Dionis_RL_Source.zip",
            file_source=zip_path,
            peer_id=message.peer_id
        )
        
        await message.answer("📦 Исходный код проекта Dionis RL:", attachment=doc)
        logging.info("Отправлен репозиторий с исходным кодом.")
    except Exception as e:
        logging.error(f"Ошибка при сборке репозитория: {e}")
        await message.answer(f"❌ Ошибка при сборке репозитория: {e}")
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

@bot.on.message(text="/статус")
async def status_handler(message: Message):
    if message.from_id != MY_VK_ID:
        return

    # 1. Загрузка ЦП и ОЗУ через psutil
    cpu_load = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    gpu_temp = "N/A"
    cpu_temp = "N/A"
    
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            if len(lines) > 0:
                last_line = lines[-1].split(",")
                
                # Для AMD Radeon RX 570 температура ГП
                if len(last_line) > 2:
                    gpu_temp = f"{float(last_line[2].strip()):.1f}°C"
                
                # Для Ryzen 7 1700 температура ЦП
                if len(last_line) > 21:
                    try:
                        raw_cpu = float(last_line[21].strip())
                        # Небольшая проверка: температура работающего Ryzen обычно между 30 и 95 градусами
                        if 25 < raw_cpu < 105:
                            cpu_temp = f"{raw_cpu:.1f}°C"
                        else:
                            # Если на 21 индексе другое число, пробуем индекс 20 (зависит от версии Afterburner)
                            raw_cpu_alt = float(last_line[20].strip())
                            if 25 < raw_cpu_alt < 105:
                                cpu_temp = f"{raw_cpu_alt:.1f}°C"
                    except ValueError:
                        pass

        # Если Afterburner почему-то не отдал температуру ЦП, ставим адекватную заглушку для Ryzen
        if cpu_temp == "N/A":
            # Вычисляем примерную температуру на основе нагрузки (для красоты вывода)
            base_temp = 38.0 if cpu_load < 20 else (50.0 if cpu_load < 70 else 68.0)
            cpu_temp = f"{base_temp + (cpu_load * 0.2):.1f}°C (эмуляция)"

    except Exception as e:
        logging.error(f"Ошибка чтения статуса железа AMD: {e}")

    report = (
        f"📊 Состояние системы:\n"
        f"💻 ЦП загрузка: {cpu_load}%\n"
        f"🔥 ЦП температура: {cpu_temp}\n"
        f"🧠 ОЗУ: {ram}%\n"
        f"🔥 ГП температура: {gpu_temp}"
    )
    await message.answer(report)

@bot.on.message(text="/выкл")
async def shutdown_command(message: Message):
    if message.from_id == MY_VK_ID:
        await message.answer("🚀 Команда принята. Выключаю 'Ковчег'...")
        os.system("shutdown /s /t 1")

@bot.on.message()
async def audio_handler(message: Message):
    audio_url = None
    
    # Сначала ищем вложения в самом сообщении
    attachments = message.attachments or []
    logging.info(f"Получено сообщение от {message.from_id} с {len(attachments)} вложениями.")
    
    # Если вложений нет, проверяем пересланные сообщения (fwd_messages)
    if not attachments and message.fwd_messages:
        # Берем вложения из первого пересланного сообщения
        attachments = message.fwd_messages[0].attachments
        logging.info(f"Проверяем пересланное сообщение, найдено {len(attachments)} вложений.")
    
    # Если и там нет, проверяем "ответ" на сообщение (reply_message)
    if not attachments and message.reply_message:
        attachments = message.reply_message.attachments
        logging.info(f"Проверяем ответ на сообщение, найдено {len(attachments)} вложений.")

    # Теперь ищем аудио в списке вложений
    doc_id_full = None # Для хранения ID в формате ownerid_id
    for attachment in attachments:
        if attachment.audio_message:
            audio_url = attachment.audio_message.link_ogg
            logging.info(f"Найдена аудиозапись в формате OGG: {audio_url}")
            break
        if audio_url:
            break
        elif attachment.audio and hasattr(attachment.audio, 'url'):
            audio_url = attachment.audio.url
            logging.info(f"Найдена аудиозапись с прямой ссылкой: {audio_url}")
            break
        elif attachment.doc:
            # Если это mp3 или mp4, берем его ID
            if attachment.doc.ext.lower() in ["mp3", "mp4", "ogg", "mpeg"]:
                doc_id_full = f"{attachment.doc.owner_id}_{attachment.doc.id}"
                audio_url = attachment.doc.url # Оставляем как запасной вариант
                logging.info(f"Найден документ: {doc_id_full}")
                break

    if audio_url:
        current_tasks = r.get("dionis_active_tasks")
        current_tasks = int(current_tasks) if current_tasks else 0

        if current_tasks >= LIMIT:
            await message.answer(
                f"⚠️ Пит-лейн переполнен! Сейчас в обработке {current_tasks} аудио.\n"
                "Пожалуйста, подожди пару минут, пока освободится место."
            )
            logging.info("Пит-лейн переполнен, отправлено уведомление пользователю.")
            return

        # Если место есть — занимаем его и отправляем задачу
        r.incr("dionis_active_tasks")
        await message.answer("🎙 Нашел аудио. Начинаю расшифровку...")
        logging.info(f"Отправляем задачу на транскрипцию: {audio_url} (doc_id: {doc_id_full})")
        transcribe_vk_audio_task.delay(audio_url, message.peer_id, doc_id=doc_id_full) #[cite: 2]
    else:
        logging.info("Аудио не найдено в сообщении.")
        # Оставляем реакцию на обычный текст, чтобы понимать, что бот жив
        if message.text.lower() in ["привет", "начать"]:
            await message.answer("Привет! Отправь мне голосовое сообщение (можно пересланное), и я его расшифрую.")
        

if __name__ == "__main__":
    # Запуск мониторинга в отдельном потоке
    monitor_thread = threading.Thread(target=monitor_logic, daemon=True)
    monitor_thread.start()
    
    logging.basicConfig(level=logging.INFO)
    bot.run_forever()
    
