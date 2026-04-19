# Dionis RL-VK-

Краткое описание: Бот расшифровывает аудио.

Принцип работы: пользователь отправляет голосовое сообщение, бот принимает его и отправляет на Celery, далее на Whisper, по окончании расшифровки отправляет боту и тот пользователю.

Технологический стек:

-Язык: Python 3.12

-Библиотеки: в requirements.txt

-ML: OpenAI Whisper (Local Edition)

-Task Queue: Celery + Redis (для параллельной обработки)

Ключевые фичи:

-Локальная расшифровка аудио (Whisper).

-Мгновенный отклик бота благодаря очереди задач.

Установка и запуск:

pip install -r requirements.txt;

python -m celery -A tasks_vk worker --loglevel=info -P solo;

python vk_bot;
