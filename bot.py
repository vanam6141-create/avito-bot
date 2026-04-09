import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from flask import Flask, request
from threading import Thread
import sqlite3
from datetime import datetime

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8712025256:AAGKjFD6FqqOdmuZtvLkDTbkpywAQJn_p7g"
ADMIN_ID = 5188679965
WEBHOOK_URL = "https://avito-bot.onrender.com/webhook"  # ЗАМЕНИТЕ ПОСЛЕ ДЕПЛОЯ

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('avito_bot.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        registered_at TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        url TEXT,
        reward INTEGER,
        status TEXT,
        created_at TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_id INTEGER,
        screenshot TEXT,
        status TEXT,
        created_at TEXT
    )
''')
conn.commit()

# ========== FLASK ДЛЯ RENDER ==========
app_flask = Flask(__name__)

@app_flask.route('/health', methods=['GET'])
def health():
    return 'OK', 200

@app_flask.route('/webhook', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    await bot_app.process_update(update)
    return 'OK', 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

# ========== TELEGRAM БОТ ==========
async def start(update: Update, context):
    user = update.effective_user
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, str(datetime.now())))
        conn.commit()
    
    keyboard = [
        [{"text": "📋 Взять задание"}],
        [{"text": "👤 Мой профиль"}],
        [{"text": "🛠 Админ панель"}]
    ]
    reply_markup = {"keyboard": keyboard, "resize_keyboard": True}
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот для заработка на отзывах на Авито.\n"
        f"💰 За один отзыв плачу до 100 рублей.\n\n"
        f"Нажми «📋 Взять задание», чтобы начать!",
        reply_markup=reply_markup
    )

async def take_task(update: Update, context):
    cursor.execute("SELECT * FROM tasks WHERE status = 'pending' LIMIT 1")
    task = cursor.fetchone()
    
    if not task:
        await update.message.reply_text("😕 Заданий пока нет. Зайдите позже!")
        return
    
    task_id, title, url, reward, status, created_at = task
    cursor.execute("UPDATE tasks SET status = 'taken' WHERE id = ?", (task_id,))
    conn.commit()
    
    keyboard = [
        [{"text": "✅ Выполнено", "callback_data": f"done_{task_id}"}],
        [{"text": "❌ Отказаться", "callback_data": f"cancel_{task_id}"}]
    ]
    reply_markup = {"inline_keyboard": keyboard}
    
    await update.message.reply_text(
        f"📋 *Ваше задание:*\n\n"
        f"🏷 *Товар:* {title}\n"
        f"💰 *Награда:* {reward}₽\n\n"
        f"🔗 *Ссылка:* {url}\n\n"
        f"📝 Как выполнить:\n"
        f"1. Перейдите по ссылке\n"
        f"2. Посмотрите объявление 30 секунд\n"
        f"3. Напишите продавцу\n"
        f"4. Оставьте отзыв\n"
        f"5. Нажмите «Выполнено» и пришлите скриншот",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def my_profile(update: Update, context):
    user_id = update.effective_user.id
    cursor.execute("SELECT COUNT(*) FROM completions WHERE user_id = ? AND status = 'approved'", (user_id,))
    completed = cursor.fetchone()[0]
    earned = completed * 100
    
    await update.message.reply_text(
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Имя: {update.effective_user.first_name}\n"
        f"✅ Выполнено заданий: {completed}\n"
        f"💰 Заработано: {earned}₽",
        parse_mode="Markdown"
    )

async def admin_panel(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет доступа!")
        return
    
    users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    tasks_taken = cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'taken'").fetchone()[0]
    tasks_done = cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0]
    
    await update.message.reply_text(
        f"🛠 *Админ панель*\n\n"
        f"📊 *Статистика*\n"
        f"─ Пользователей: {users_count}\n"
        f"─ Заданий в работе: {tasks_taken}\n"
        f"─ Завершённых: {tasks_done}\n\n"
        f"📝 *Команды:*\n"
        f"/add Название | ссылка | награда\n"
        f"/list — список заданий",
        parse_mode="Markdown"
    )

async def add_task(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = update.message.text.replace("/add", "").strip()
    parts = text.split("|")
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Формат: `/add Название | ссылка | 100`", parse_mode="Markdown")
        return
    
    title = parts[0].strip()
    url = parts[1].strip()
    reward = int(parts[2].strip()) if len(parts) > 2 else 100
    
    cursor.execute(
        "INSERT INTO tasks (title, url, reward, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (title, url, reward, 'pending', str(datetime.now()))
    )
    conn.commit()
    
    await update.message.reply_text(f"✅ Задание добавлено!\n🏷 {title}\n💰 {reward}₽")

async def list_tasks(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    cursor.execute("SELECT id, title, status FROM tasks")
    tasks = cursor.fetchall()
    
    if not tasks:
        await update.message.reply_text("📋 Заданий нет")
        return
    
    result = "📋 *Список заданий:*\n\n"
    for task in tasks:
        status_icon = "🟢" if task[2] == 'pending' else "🟡" if task[2] == 'taken' else "🔵"
        result += f"{status_icon} #{task[0]} — {task[1]} — {task[2]}\n"
    
    await update.message.reply_text(result, parse_mode="Markdown")

async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("done_"):
        task_id = int(query.data.split("_")[1])
        cursor.execute(
            "INSERT INTO completions (user_id, task_id, status, created_at) VALUES (?, ?, ?, ?)",
            (query.from_user.id, task_id, 'pending', str(datetime.now()))
        )
        conn.commit()
        await query.message.reply_text("📸 *Отправьте скриншот отзыва* (фото)\n\nПосле проверки админ одобрит выплату.", parse_mode="Markdown")
    
    elif query.data.startswith("cancel_"):
        task_id = int(query.data.split("_")[1])
        cursor.execute("UPDATE tasks SET status = 'pending' WHERE id = ?", (task_id,))
        conn.commit()
        await query.message.reply_text("❌ Задание отменено. Вы можете взять другое.")

async def handle_photo(update: Update, context):
    cursor.execute(
        "SELECT c.id, c.task_id, t.title, t.reward FROM completions c "
        "JOIN tasks t ON c.task_id = t.id "
        "WHERE c.user_id = ? AND c.status = 'pending'",
        (update.effective_user.id,)
    )
    completion = cursor.fetchone()
    
    if not completion:
        await update.message.reply_text("У вас нет заданий, ожидающих проверки.")
        return
    
    comp_id, task_id, title, reward = completion
    
    photo = update.message.photo[-1]
    photo_id = photo.file_id
    cursor.execute("UPDATE completions SET screenshot = ?, status = 'waiting' WHERE id = ?", (photo_id, comp_id))
    conn.commit()
    
    await context.bot.send_message(
        ADMIN_ID,
        f"📝 *Новый отзыв на проверку*\n\n"
        f"👤 Пользователь: {update.effective_user.first_name} (@{update.effective_user.username})\n"
        f"📋 Задание: {title}\n"
        f"💰 Награда: {reward}₽"
    )
    await context.bot.send_photo(ADMIN_ID, photo_id)
    
    await update.message.reply_text("✅ Скриншот отправлен на проверку!")

async def echo(update: Update, context):
    await update.message.reply_text("Используйте кнопки внизу экрана 👇")

# ========== ЗАПУСК ==========
def setup_application():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📋 Взять задание"), take_task))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("👤 Мой профиль"), my_profile))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("🛠 Админ панель"), admin_panel))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    return app

if __name__ == "__main__":
    bot_app = setup_application()
    
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    
    async def start_webhook():
        await bot_app.bot.set_webhook(WEBHOOK_URL)
        print(f"✅ Webhook установлен на {WEBHOOK_URL}")
    
    asyncio.run(start_webhook())
    
    print("🚀 Бот запущен на Render!")
    bot_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=WEBHOOK_URL
    )