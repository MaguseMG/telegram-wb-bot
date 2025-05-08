import logging
import json
import os
import requests
from threading import Thread

# Добавляем Flask для веб-сервера
from flask import Flask

# Импорт Telegram-бота
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    ConversationHandler,
    Job
)

# --- Настройка Flask-сервера для Uptime Robot ---
app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

def keep_alive():
    """Запускает Flask-сервер в отдельном потоке."""
    t = Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    t.start()

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

DATA_FILE = "data.json"  # Файл для хранения данных

# Состояния диалога
MAIN_MENU, ADD_CABINET_NAME, ADD_CABINET_KEY, EDIT_CABINET, SELECT_CABINET_FOR_EDIT, SELECT_CABINET_FOR_CAMPAIGNS, SELECT_CABINET_FOR_TRACKING = range(7)

MAX_CABINETS = 3

# --- Функции для хранения данных через JSON ---
def save_data(data: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error("Ошибка сохранения данных: %s", e, exc_info=True)

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Ошибка загрузки данных: %s", e, exc_info=True)
    return {}

def persist_user_data(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    all_data = load_data()
    all_data[chat_id] = {
        "cabinets": context.user_data.get("cabinets", []),
        "tracking": context.user_data.get("tracking", {}),
        "campaign_states": context.user_data.get("campaign_states", {})
    }
    save_data(all_data)

# --- Функция для разбиения длинного текста на части ---
def split_message(text, max_length=4096):
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        split_index = text.rfind("\n", 0, max_length)
        if split_index == -1:
            split_index = max_length
        parts.append(text[:split_index])
        text = text[split_index:]
    return parts

# --- Главное меню ---
def get_main_keyboard():
    keyboard = [
        ["Добавить кабинет", "Редактировать кабинет"],
        ["Показать кампании", "Отслеживание кабинета"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def start(update: Update, context: CallbackContext) -> int:
    chat_id = str(update.effective_chat.id)
    all_data = load_data()
    if chat_id in all_data:
        context.user_data.update(all_data[chat_id])
    else:
        context.user_data["cabinets"] = []
        context.user_data["tracking"] = {}
        context.user_data["campaign_states"] = {}
    update.message.reply_text(
        "Добро пожаловать! Вы в главном меню.",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

def main_menu_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()

    if text == "добавить кабинет":
        if len(context.user_data.get("cabinets", [])) >= MAX_CABINETS:
            update.message.reply_text(
                f"У вас уже {MAX_CABINETS} кабинетов. Для изменения выберите «Редактировать кабинет».",
                reply_markup=get_main_keyboard()
            )
            return MAIN_MENU
        update.message.reply_text(
            "Введите название нового кабинета (например, «Основной»):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_CABINET_NAME

    elif text == "редактировать кабинет":
        cabinets = context.user_data.get("cabinets", [])
        if not cabinets:
            update.message.reply_text(
                "Нет сохранённых кабинетов. Сначала добавьте кабинет.",
                reply_markup=get_main_keyboard()
            )
            return MAIN_MENU
        kb = [[cab["name"]] for cab in cabinets]
        kb.append(["Отмена"])
        update.message.reply_text(
            "Выберите кабинет для редактирования:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SELECT_CABINET_FOR_EDIT

    elif text == "показать кампании":
        cabinets = context.user_data.get("cabinets", [])
        if not cabinets:
            update.message.reply_text(
                "Нет сохранённых кабинетов. Добавьте кабинет!",
                reply_markup=get_main_keyboard()
            )
            return MAIN_MENU
        kb = [[cab["name"]] for cab in cabinets]
        kb.append(["Отмена"])
        update.message.reply_text(
            "Выберите кабинет для просмотра кампаний:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SELECT_CABINET_FOR_CAMPAIGNS

    elif text == "отслеживание кабинета":
        cabinets = context.user_data.get("cabinets", [])
        if not cabinets:
            update.message.reply_text(
                "Нет сохранённых кабинетов. Добавьте кабинет!",
                reply_markup=get_main_keyboard()
            )
            return MAIN_MENU
        # Формируем клавиатуру с эмодзи: если отслеживание включено — ✅, иначе — ❌
        tracking = context.user_data.get("tracking", {})
        kb = []
        for cab in cabinets:
            status = tracking.get(cab["name"], False)
            emoji = "✅" if status else "❌"
            kb.append([f"{cab['name']} {emoji}"])
        kb.append(["Отмена"])
        update.message.reply_text(
            "Выберите кабинет для включения/отключения отслеживания:",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
        )
        return SELECT_CABINET_FOR_TRACKING

    else:
        update.message.reply_text("Используйте кнопки меню.", reply_markup=get_main_keyboard())
        return MAIN_MENU

# --- Добавление нового кабинета ---
def add_cabinet_name(update: Update, context: CallbackContext) -> int:
    cabinet_name = update.message.text.strip()
    context.user_data["temp_cabinet_name"] = cabinet_name
    update.message.reply_text(
        f"Название: «{cabinet_name}». Теперь введите WB API ключ для этого кабинета:",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_CABINET_KEY

def add_cabinet_key(update: Update, context: CallbackContext) -> int:
    wb_key = update.message.text.strip()
    cabinet_name = context.user_data.get("temp_cabinet_name", "Без названия")
    new_cab = {"name": cabinet_name, "key": wb_key}
    context.user_data.setdefault("cabinets", []).append(new_cab)
    context.user_data.setdefault("tracking", {})[cabinet_name] = False
    persist_user_data(update, context)
    update.message.reply_text(
        f"Кабинет «{cabinet_name}» добавлен!",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

# --- Редактирование кабинета ---
def select_cabinet_for_edit(update: Update, context: CallbackContext) -> int:
    chosen = update.message.text.strip()
    if chosen.lower() == "отмена":
        update.message.reply_text("Отмена редактирования.", reply_markup=get_main_keyboard())
        return MAIN_MENU
    cabinets = context.user_data.get("cabinets", [])
    for i, cab in enumerate(cabinets):
        if cab["name"].lower() == chosen.lower():
            context.user_data["edit_index"] = i
            update.message.reply_text(
                f"Вы выбрали кабинет «{cab['name']}» для редактирования.\n"
                "Введите новое название (или отправьте текущее, если менять не нужно):",
                reply_markup=ReplyKeyboardRemove()
            )
            return EDIT_CABINET
    update.message.reply_text("Кабинет не найден.", reply_markup=get_main_keyboard())
    return MAIN_MENU

def edit_cabinet(update: Update, context: CallbackContext) -> int:
    new_name = update.message.text.strip()
    idx = context.user_data.get("edit_index")
    if idx is None:
        update.message.reply_text("Ошибка: не выбран кабинет.", reply_markup=get_main_keyboard())
        return MAIN_MENU
    old_name = context.user_data["cabinets"][idx]["name"]
    context.user_data["cabinets"][idx]["name"] = new_name
    tracking = context.user_data.get("tracking", {})
    tracking[new_name] = tracking.pop(old_name, False)
    persist_user_data(update, context)
    update.message.reply_text(f"Кабинет изменён. Новое название: «{new_name}».", reply_markup=get_main_keyboard())
    return MAIN_MENU

# --- Показ кампаний ---
def select_cabinet_for_campaigns(update: Update, context: CallbackContext) -> int:
    chosen = update.message.text.strip()
    if chosen.lower() == "отмена":
        update.message.reply_text("Возврат в меню.", reply_markup=get_main_keyboard())
        return MAIN_MENU
    for cab in context.user_data.get("cabinets", []):
        if cab["name"].lower() == chosen.lower():
            result_msg = get_campaigns_for_cabinet(cab["key"])
            for part in split_message(result_msg):
                update.message.reply_text(part, reply_markup=get_main_keyboard())
            return MAIN_MENU
    update.message.reply_text("Кабинет не найден.", reply_markup=get_main_keyboard())
    return MAIN_MENU

# --- Отслеживание кабинета ---
def select_cabinet_for_tracking(update: Update, context: CallbackContext) -> int:
    chosen = update.message.text.strip()
    if chosen.lower() == "отмена":
        update.message.reply_text("Возврат в меню.", reply_markup=get_main_keyboard())
        return MAIN_MENU
    cabinets = context.user_data.get("cabinets", [])
    target_cab = None
    for cab in cabinets:
        if chosen.startswith(cab["name"]):
            target_cab = cab
            break
    if not target_cab:
        update.message.reply_text("Кабинет не найден.", reply_markup=get_main_keyboard())
        return MAIN_MENU
    current = context.user_data.get("tracking", {}).get(target_cab["name"], False)
    new_status = not current
    context.user_data["tracking"][target_cab["name"]] = new_status
    persist_user_data(update, context)
    msg = f"Отслеживание для кабинета «{target_cab['name']}» {'включено ✅' if new_status else 'выключено ❌'}."
    update.message.reply_text(msg, reply_markup=get_main_keyboard())
    if new_status:
        job_name = f"track_{update.effective_chat.id}_{target_cab['name']}"
        context.job_queue.run_repeating(
            callback=track_campaign_changes,
            interval=60,
            first=5,
            context={'chat_id': update.effective_chat.id, 'cabinet': target_cab},
            name=job_name
        )
    return MAIN_MENU

# --- Запрос кампаний (вывод только названия и статуса с эмодзи) ---
def get_campaigns_for_cabinet(wb_api_key: str) -> str:
    url = (
        "https://advert-api.wildberries.ru/adv/v1/promotion/adverts"
        "?type=8,9&status=9,11&order=change&direction=asc"
    )
    headers = {
        "Authorization": wb_api_key,
        "User-Agent": "PostmanRuntime/7.43.3",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Content-Length": "0"
    }
    try:
        resp = requests.post(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                campaigns = data
            else:
                campaigns = data.get("adverts", [])
            if not campaigns:
                return "Нет кампаний по заданным параметрам."
            status_map = {
                9: "Активна ✅",
                11: "Приостановлена ❌"
            }
            parts = []
            for camp in campaigns:
                name = camp.get("name", "—")
                st = camp.get("status", 0)
                parts.append(f"Название: {name}\nСтатус: {status_map.get(st, st)}\n")
            return "\n".join(parts)
        else:
            return f"Ошибка {resp.status_code}:\n{resp.text}"
    except Exception as e:
        logger.error("Ошибка при запросе кампаний: %s", e, exc_info=True)
        return "Произошла ошибка при получении кампаний."

# --- Периодическая проверка изменений статусов для конкретного кабинета ---
def track_campaign_changes(context: CallbackContext):
    job_context = context.job.context
    chat_id = job_context.get('chat_id')
    cabinet = job_context.get('cabinet')
    wb_api_key = cabinet.get("key")
    cab_name = cabinet.get("name")
    url = (
        "https://advert-api.wildberries.ru/adv/v1/promotion/adverts"
        "?type=8,9&status=9,11&order=change&direction=asc"
    )
    headers = {
        "Authorization": wb_api_key,
        "User-Agent": "PostmanRuntime/7.43.3",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "Content-Length": "0"
    }
    try:
        resp = requests.post(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                campaigns = data
            else:
                campaigns = data.get("adverts", [])
            user_data = context.dispatcher.user_data.get(str(chat_id), {})
            prev_states = user_data.get("campaign_states", {}).get(cab_name, {})
            current_states = {}
            changed = []
            for camp in campaigns:
                adv_id = camp.get("advertId")
                st = camp.get("status")
                current_states[adv_id] = st
                old = prev_states.get(adv_id)
                if old == 9 and st == 11:
                    changed.append(f"Кампания «{camp.get('name', '—')}» стала Приостановленной ❌")
            campaign_states = user_data.get("campaign_states", {})
            campaign_states[cab_name] = current_states
            user_data["campaign_states"] = campaign_states
            context.dispatcher.user_data[str(chat_id)] = user_data
            if changed:
                message = f"Изменения в кабинете «{cab_name}»:\n" + "\n".join(changed)
                for part in split_message(message):
                    context.bot.send_message(chat_id=chat_id, text=part)
        else:
            logger.warning("track_campaign_changes: %s %s", resp.status_code, resp.text)
    except Exception as e:
        logger.error("track_campaign_changes error: %s", e, exc_info=True)

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Диалог отменён. /start — чтобы начать заново.",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

# --- Главное меню (повторно) ---
def get_main_keyboard():
    keyboard = [
        ["Добавить кабинет", "Редактировать кабинет"],
        ["Показать кампании", "Отслеживание кабинета"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def main():
    # Запускаем Flask-сервер для Uptime Robot
    keep_alive()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                MessageHandler(Filters.text & ~Filters.command, main_menu_handler)
            ],
            ADD_CABINET_NAME: [
                MessageHandler(Filters.text & ~Filters.command, add_cabinet_name)
            ],
            ADD_CABINET_KEY: [
                MessageHandler(Filters.text & ~Filters.command, add_cabinet_key)
            ],
            SELECT_CABINET_FOR_EDIT: [
                MessageHandler(Filters.text & ~Filters.command, select_cabinet_for_edit)
            ],
            EDIT_CABINET: [
                MessageHandler(Filters.text & ~Filters.command, edit_cabinet)
            ],
            SELECT_CABINET_FOR_CAMPAIGNS: [
                MessageHandler(Filters.text & ~Filters.command, select_cabinet_for_campaigns)
            ],
            SELECT_CABINET_FOR_TRACKING: [
                MessageHandler(Filters.text & ~Filters.command, select_cabinet_for_tracking)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
