from flask import (
    Flask,
    render_template,
    send_from_directory,
    request,
    session,
    jsonify,
)
from flask_wtf.csrf import CSRFProtect
from config import Config
from bot import NotificationBot
from datetime import datetime, timedelta
from typing import Dict, List
import os
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Загрузка переменных окружения
load_dotenv()

# Инициализация Flask приложения
app = Flask(__name__)
app.config.from_object(Config)
csrf = CSRFProtect(app)

# Константы для сообщений
ERROR_MESSAGES = {
    "rate_limit": "Слишком много запросов. Пожалуйста, попробуйте позже.",
    "privacy_required": "Необходимо согласиться с условиями обработки данных",
    "invalid_name": "Имя обязательно для заполнения",
    "invalid_phone": "Телефон обязателен для заполнения",
    "phone_length": "Телефон должен содержать 10 цифр",
    "name_too_short": "Имя слишком короткое",
    "fake_name": "Пожалуйста, введите реальное имя",
    "submit_error": "Не удалось отправить заявку",
}

# Инициализация бота
telegram_bot = NotificationBot(
    token=app.config["TELEGRAM_BOT_TOKEN"],
    password=app.config["TELEGRAM_BOT_PASSWORD"],
    admin_chat_id=app.config["TELEGRAM_CHAT_ID"],
)
telegram_bot.run_in_thread()


def validate_phone(phone: str) -> str:
    """Очистка и валидация номера телефона"""
    return "".join(filter(str.isdigit, phone))[-10:]


def format_phone(phone: str) -> str:
    """Форматирование номера для отображения"""
    return f"+7 ({phone[:3]}) {phone[3:6]}-{phone[6:8]}-{phone[8:]}"


def build_telegram_message(data: Dict) -> str:
    """Формирование сообщения для Telegram"""
    parts = [
        f"📌 Новая заявка с сайта:",
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"👤 Имя: {data['firstname']}",
    ]

    if lastname := data.get("lastname"):
        parts.append(f"👤 Фамилия: {lastname}")
    if patronymic := data.get("patronymic"):
        parts.append(f"👤 Отчество: {patronymic}")

    parts.extend(
        [
            f"📞 Телефон: {format_phone(data['phone'])}",
            f"📝 Сообщение: {data.get('message', '').strip() or 'не указано'}",
        ]
    )

    return "\n".join(parts)


def send_to_telegram(data: Dict) -> bool:
    """Отправка данных в Telegram"""
    try:
        message = build_telegram_message(data)
        return telegram_bot.send_message(message)
    except Exception as e:
        logging.error(f"Ошибка отправки в Telegram: {e}")
        return False


def check_request_limit(ip: str) -> bool:
    now = datetime.now()
    requests = session.get("requests", [])
    window = timedelta(seconds=app.config["REQUEST_WINDOW"])
    requests = [r for r in requests if now - r < window]

    if len(requests) >= app.config["REQUEST_LIMIT"]:
        return False

    requests.append(now)
    session["requests"] = requests
    return True


def validate_form_data(data: Dict) -> List[str]:
    """Валидация данных формы"""
    errors = []

    if not data["firstname"]:
        errors.append(ERROR_MESSAGES["invalid_name"])
    if not data["phone"]:
        errors.append(ERROR_MESSAGES["invalid_phone"])
    elif len(data["phone"]) != 10:
        errors.append(ERROR_MESSAGES["phone_length"])
    elif len(data["firstname"]) < 2:
        errors.append(ERROR_MESSAGES["name_too_short"])
    elif data["firstname"].lower() in ["тест", "пример"]:
        errors.append(ERROR_MESSAGES["fake_name"])

    return errors


@app.route("/submit-feedback", methods=["POST"])
def submit_feedback():
    """Обработчик отправки формы обратной связи"""
    if not check_request_limit(request.remote_addr):
        return jsonify({"error": ERROR_MESSAGES["rate_limit"]}), 429

    if not request.form.get("privacy"):
        return jsonify({"error": ERROR_MESSAGES["privacy_required"]}), 400

    form_data = {
        "firstname": request.form.get("firstname", "").strip(),
        "lastname": request.form.get("lastname", "").strip(),
        "patronymic": request.form.get("patronymic", "").strip(),
        "phone": validate_phone(request.form.get("phone", "")),
        "message": request.form.get("message", "").strip(),
    }

    if errors := validate_form_data(form_data):
        return jsonify({"error": " ".join(errors)}), 400

    try:
        if send_to_telegram(form_data):
            return jsonify({"success": True})
        return jsonify({"error": ERROR_MESSAGES["submit_error"]}), 500
    except Exception as e:
        logging.error(f"Ошибка при обработке формы: {e}")
        return jsonify({"error": str(e)}), 500


# Стандартные роуты
@app.route("/feedback_content")
def feedback_content():
    return render_template("feedback_content.html")


@app.route("/feedback-success")
def feedback_success():
    return "Спасибо! Ваша заявка принята. Мы свяжемся с вами в ближайшее время."


@app.route("/feedback-error")
def feedback_error():
    return "Произошла ошибка при отправке заявки. Пожалуйста, попробуйте позже."


@app.route("/")
def home():
    return render_template("main.html", active_page="main")


@app.route("/about")
def about():
    return render_template("about.html", active_page="about")


@app.route("/tovari")
def tovari():
    return render_template("tovari.html")


@app.route("/contacts")
def contacts():
    return render_template("contacts.html", active_page="contacts")


@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html", active_page="privacy_policy")


# Статические файлы
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static", "favicon"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


# Админские функции
@app.route("/admin/update_password", methods=["POST"])
def update_bot_password():
    """Обновление пароля бота"""
    auth_header = request.headers.get("Authorization")
    if auth_header != app.config["SECRET_KEY"]:
        return {"status": "error", "message": "Unauthorized"}, 401

    if not request.json or "new_password" not in request.json:
        return {"status": "error", "message": "Неверные данные"}, 400

    try:
        telegram_bot.update_password(request.json["new_password"])
        return {
            "status": "success",
            "message": "Пароль успешно обновлен. Все пользователи деавторизованы.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route("/submit-order", methods=["POST"])
@csrf.exempt
def submit_order():
    try:
        data = request.get_json()

        # Валидация данных
        if not data.get("name") or not data.get("phone"):
            return jsonify({"error": "Не заполнены обязательные поля"}), 400

        phone = data["phone"]
        if len(phone) != 10 or not phone.isdigit():
            return jsonify({"error": "Неверный формат телефона"}), 400

        # Формирование сообщения
        message = [
            "📦 НОВЫЙ ЗАКАЗ",
            f"👤 Имя: {data['name']}",
            f"📞 Телефон: +7 ({phone[:3]}) {phone[3:6]}-{phone[6:8]}-{phone[8:]}",
            f"💬 Комментарий: {data.get('comment', 'не указан')}",
            "",
            "🛒 Состав заказа:",
            *[
                f"- {i['name']}: {i['quantity']} {i['unit']} × {i['pricePerUnit']} ₽ = {i['price']} ₽"
                for i in data["order"]["items"]
            ],
            "",
            f"💰 Итого: {data['order']['total']} ₽",
            f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ]

        if telegram_bot.send_message("\n".join(message)):
            return jsonify({"success": True})
        return jsonify({"error": "Ошибка при отправке заказа"}), 500

    except Exception as e:
        logging.error(f"Ошибка при обработке заказа: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера"}), 500


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("\nПолучен сигнал завершения...")
    finally:
        print("Остановка бота...")
        telegram_bot.shutdown()
        print("Программа завершена.")
