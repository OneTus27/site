import os
import secrets
from dotenv import load_dotenv

# Загружаем .env в самом начале
load_dotenv()


class Config:
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

    # Секретный ключ
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(16)

    # Обязательные настройки Telegram
    try:
        TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
        TELEGRAM_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
        TELEGRAM_BOT_PASSWORD = os.environ["TELEGRAM_BOT_PASSWORD"]
    except KeyError as e:
        raise RuntimeError(f"Необходимо задать переменную окружения: {e.args[0]}")

    # Авторизованные пользователи (в памяти)
    TELEGRAM_AUTHORIZED_USERS = {}

    # Настройки защиты от спама
    REQUEST_LIMIT = 3
    REQUEST_WINDOW = 60
