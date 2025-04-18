import asyncio
import json
import logging
import os
import threading
import requests
from typing import Set, Optional

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv, set_key

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class NotificationBot:
    def __init__(self, token: str, password: str, admin_chat_id: int):
        """Инициализация бота для уведомлений

        Args:
            token: Токен бота от BotFather
            password: Пароль для авторизации администратора
            admin_chat_id: ID чата администратора
        """
        if not token or not isinstance(token, str):
            raise ValueError("Неверный токен бота")
        if not password or not isinstance(password, str):
            raise ValueError("Неверный пароль")
        if not isinstance(admin_chat_id, int):
            raise ValueError("ID чата должно быть числом")

        self.token = token
        self._password = password
        self.admin_chat_id = admin_chat_id
        self._auth_file = os.path.join(os.path.dirname(__file__), "auth_users.json")
        self.authorized_users = self._load_authorized_users()
        self.application = None
        self._stop_event = threading.Event()
        self._bot_thread = None
        self._env_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".env")
        )

    def _load_authorized_users(self) -> Set[int]:
        """Загрузка авторизованных пользователей из файла"""
        try:
            if os.path.exists(self._auth_file):
                with open(self._auth_file, "r") as f:
                    return set(json.load(f))
        except Exception as e:
            logger.error(f"Ошибка загрузки авторизованных пользователей: {e}")
        return set()

    def _save_authorized_users(self) -> None:
        """Сохранение авторизованных пользователей в файл"""
        try:
            with open(self._auth_file, "w") as f:
                json.dump(list(self.authorized_users), f)
        except Exception as e:
            logger.error(f"Ошибка сохранения авторизованных пользователей: {e}")

    async def verify_user(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Проверка пароля пользователя"""
        chat_id = update.message.chat.id

        if chat_id != self.admin_chat_id:
            await update.message.reply_text("❌ Доступ запрещен")
            return

        if (
            isinstance(update.message.text, str)
            and update.message.text == self._password
        ):
            self.authorized_users.add(chat_id)
            self._save_authorized_users()
            await update.message.reply_text("🔐 Доступ разрешен")
            logger.info(f"Пользователь {chat_id} успешно авторизован")
        else:
            await update.message.reply_text("❌ Неверный пароль")
            logger.warning(f"Неудачная попытка входа с ID {chat_id}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        await update.message.reply_text("🔑 Введите пароль для доступа:")
        logger.info(f"Получена команда /start от {update.message.chat.id}")

    def send_message(self, message_text: str) -> bool:
        """Отправка сообщения авторизованным пользователям

        Args:
            message_text: Текст сообщения для отправки

        Returns:
            bool: True если сообщение отправлено успешно
        """
        if not self.authorized_users:
            logger.warning("Попытка отправки без авторизованных пользователей")
            return False

        success = False
        for chat_id in self.authorized_users:
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": chat_id, "text": message_text},
                    timeout=5,
                )
                if response.status_code == 200:
                    success = True
                    logger.info(f"Сообщение отправлено в чат {chat_id}")
                else:
                    logger.error(f"Ошибка отправки в чат {chat_id}: {response.text}")
            except Exception as e:
                logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

        return success

    async def _run_bot(self) -> None:
        """Основной цикл работы бота"""
        try:
            self.application = ApplicationBuilder().token(self.token).build()

            # Добавляем обработчики команд
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.verify_user)
            )

            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()

            logger.info("Бот запущен и готов к работе")

            while not self._stop_event.is_set():
                await asyncio.sleep(1)

        except Exception as e:
            logger.critical(f"Критическая ошибка бота: {e}")
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Корректное завершение работы бота"""
        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Бот успешно остановлен")
            except Exception as e:
                logger.error(f"Ошибка при остановке бота: {e}")

    def run(self) -> None:
        """Запуск бота в основном потоке"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_bot())
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
        finally:
            logger.info("Завершение работы бота")

    def run_in_thread(self) -> None:
        """Запуск бота в отдельном потоке"""
        self._bot_thread = threading.Thread(
            target=self.run, name="TelegramBotThread", daemon=True
        )
        self._bot_thread.start()
        logger.info("Бот запущен в отдельном потоке")

    def update_password(self, new_password: str) -> None:
        """Обновление пароля администратора

        Args:
            new_password: Новый пароль для авторизации
        """
        self._password = new_password
        self.authorized_users = set()

        try:
            if os.path.exists(self._auth_file):
                os.remove(self._auth_file)
        except Exception as e:
            logger.error(f"Ошибка удаления файла авторизации: {e}")

        set_key(self._env_path, "TELEGRAM_BOT_PASSWORD", new_password)
        logger.info("Пароль успешно обновлен, все пользователи деавторизованы")

    def shutdown(self) -> None:
        """Безопасное завершение работы бота"""
        self._stop_event.set()
        if self._bot_thread and self._bot_thread.is_alive():
            self._bot_thread.join(timeout=5)
            logger.info("Поток бота завершен")
