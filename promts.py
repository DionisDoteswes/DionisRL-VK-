import os

# Путь к файлу с терминами
PROMPTS_FILE = "promts.txt"

def get_whisper_prompt():
    """Читает список терминов из текстового файла."""
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else ""
        except Exception as e:
            print(f"Ошибка при чтении файла промтов: {e}")
            return ""
    return ""
