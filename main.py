import mimetypes
import sys
import sqlite3

class imghdr:
    @staticmethod
    def what(file, h=None):
        return mimetypes.guess_type(file)[0]

sys.modules['imghdr'] = imghdr

import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import time
import threading

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ID админа
ADMIN_ID = 11111111111

# Функция для проверки прав администратора
def admin_only(func):
    def wrapper(update: Update, context: CallbackContext):
        if update.message.from_user.id != ADMIN_ID:
            update.message.reply_text(
                "Здравствуйте, вы не являетесь админом данного бота, так что в доступе отказано. "
                "Если вам необходим данный бот, то переходите сюда @YapmolaStoreBot"
            )
            return
        return func(update, context)
    return wrapper

# Функция для подключения к базе данных
def get_db_connection():
    return sqlite3.connect('bot_data.db')

# Создаем таблицы, если они не существуют
def create_tables():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image TEXT,
            text TEXT
        )
        ''')
        conn.commit()

# Подключение к базе данных
def update_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Проверяем, существует ли таблица, и добавляем столбцы, если они отсутствуют
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image TEXT,
            text TEXT
        )
        ''')
        conn.commit()

# Список каналов для рассылки
channels = []

# Пост для рассылки
post_text = ""
post_image = None

# Частота рассылки (раз в час)
frequency = 1

# Флаг для управления рассылкой
sending = False

# Флаг для ожидания поста
waiting_for_post = False

# Функция для добавления канала
@admin_only
def add_channel(update: Update, context: CallbackContext) -> None:
    channel_ids = update.message.text.split('\n')[1:]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for channel_id in channel_ids:
            cursor.execute("INSERT OR IGNORE INTO channels (channel_id) VALUES (?)", (channel_id.strip(),))
        conn.commit()
    update.message.reply_text(f"Канал(ы) {', '.join(channel_ids)} добавлен(ы) для рассылки.")

# Функция для добавления поста
@admin_only
def add_post(update: Update, context: CallbackContext) -> None:
    global waiting_for_post
    waiting_for_post = True
    update.message.reply_text("Отправьте изображение с подписью для добавления поста.")

# Функция для обработки сообщений с изображениями
@admin_only
def handle_photo(update: Update, context: CallbackContext) -> None:
    global waiting_for_post, post_text, post_image
    if waiting_for_post:
        if update.message.photo:
            post_text = update.message.caption or ""
            post_image = update.message.photo[-1].file_id
            # Сохраняем пост в базу данных
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO posts (image, text) VALUES (?, ?)", (post_image, post_text))
                conn.commit()
            update.message.reply_text("Пост добавлен для рассылки.")
            waiting_for_post = False
        else:
            update.message.reply_text("Сообщение не содержит изображения.")
    else:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")

# Функция для установки частоты рассылки
@admin_only
def set_frequency(update: Update, context: CallbackContext) -> None:
    global frequency
    frequency = int(update.message.text.split(' ')[1])
    update.message.reply_text(f"Частота рассылки установлена на {frequency} раз в час.")

# Функция для запуска рассылки
@admin_only
def start_sending(update: Update, context: CallbackContext) -> None:
    global sending
    sending = True
    update.message.reply_text("Рассылка запущена.")
    # Запускаем рассылку в отдельном потоке
    threading.Thread(target=send_posts, args=(context,), daemon=True).start()

# Функция для остановки рассылки
@admin_only
def stop_sending(update: Update, context: CallbackContext) -> None:
    global sending
    sending = False
    update.message.reply_text("Рассылка остановлена.")

# Функция для удаления всех каналов
@admin_only
def clear_channels(update: Update, context: CallbackContext) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels")
        conn.commit()
    update.message.reply_text("Все каналы удалены.")

# Функция для вывода списка каналов
@admin_only
def see_channel(update: Update, context: CallbackContext) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id FROM channels")
        channels = cursor.fetchall()
    if channels:
        channel_list = "\n".join([str(channel[0]) for channel in channels])
        update.message.reply_text(f"Каналы для рассылки:\n{channel_list}")
    else:
        update.message.reply_text("Список каналов пуст. Добавьте каналы для рассылки!")

# Функция для отправки постов
@admin_only
def send_posts(context: CallbackContext) -> None:
    global sending
    while sending:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id FROM channels")
            channels = cursor.fetchall()
            cursor.execute("SELECT image, text FROM posts ORDER BY id DESC LIMIT 1")
            post = cursor.fetchone()
        if post:
            post_image, post_text = post
            for channel in channels:
                channel_id = channel[0]
                try:
                    context.bot.send_photo(chat_id=channel_id, photo=post_image, caption=post_text)
                    logger.info(f"Пост успешно отправлен в канал: {channel_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке в канал {channel_id}: {e}")
        time.sleep(3600 / frequency)

# Функция для просмотра текущего поста
@admin_only
def see_post(update: Update, context: CallbackContext) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT image, text FROM posts ORDER BY id DESC LIMIT 1")
        post = cursor.fetchone()
    if post:
        post_image, post_text = post
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=post_image, caption="Текущий пост для рассылки:")
        context.bot.send_message(chat_id=update.effective_chat.id, text=post_text)
    else:
        update.message.reply_text("Нет активного поста для рассылки.")

# Функция для просмотра истории постов
@admin_only
def show_history(update: Update, context: CallbackContext) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT image, text FROM posts")
        posts = cursor.fetchall()
    if posts:
        update.message.reply_text("История последних постов:")
        for i, post in enumerate(posts, 1):
            post_image, post_text = post
            context.bot.send_photo(chat_id=update.effective_chat.id, photo=post_image, caption=f"Пост {i}")
            context.bot.send_message(chat_id=update.effective_chat.id, text=post_text)
    else:
        update.message.reply_text("История постов пуста.")

# Функция для команды /start
def start_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Привет! Я бот для рассылки постов в каналы или по другому Мастегинг. "
        "Отправь мне /help для просмотра команд."
    )

# Главная функция для запуска бота
def main() -> None:
    # Обновляем базу данных
    update_database()

    updater = Updater("ТОКЕН:СЮДА", use_context=True)  # Вставьте ваш токен API Telegram-бота сюда

    # Функция для команды /help
    def help_command(update: Update, context: CallbackContext) -> None:
        update.message.reply_text(
            "Команды:\n"
            "/add_channel - добавить канал для рассылки\n"
            "/add_post - добавить пост для рассылки\n"
            "/set_frequency - установить частоту рассылки отправлять в  формате /set_frequency 10 (10 означает что будет 10 постов в час)\n"
            "/send - запустить рассылку\n"
            "/stop - остановить рассылку\n"
            "/clear_channels - удалить все каналы\n"
            "/clear_post - удалить пост\n"
            "/see_channel - посмотреть список каналов\n"
            "/see_post - посмотреть текущий пост\n"
            "/history - показать историю постов\n"
        )

    # Получаем диспетчера для регистрации обработчиков
    dispatcher = updater.dispatcher

    # Регистрируем обработчики команд
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("add_channel", add_channel))
    dispatcher.add_handler(CommandHandler("add_post", add_post))
    dispatcher.add_handler(CommandHandler("set_frequency", set_frequency))
    dispatcher.add_handler(CommandHandler("send", start_sending))
    dispatcher.add_handler(CommandHandler("stop", stop_sending))
    dispatcher.add_handler(CommandHandler("clear_channels", clear_channels))
    dispatcher.add_handler(CommandHandler("see_channel", see_channel))
    dispatcher.add_handler(CommandHandler("see_post", see_post))
    dispatcher.add_handler(CommandHandler("history", show_history))
    dispatcher.add_handler(MessageHandler(Filters.photo & ~Filters.command, handle_photo))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Запускаем бота
    updater.start_polling()

    # Ожидаем завершения работы бота
    updater.idle()

if __name__ == '__main__':
    create_tables()
    main()
