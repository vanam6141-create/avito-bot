from __future__ import annotations

import logging
import re

from telegram import BotCommand, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .db import Database

LOG = logging.getLogger("avito_sniper_ai")
QUERY_RE = re.compile(r"^/addsearch\s+(.+)$", re.IGNORECASE | re.DOTALL)

MENU = ReplyKeyboardMarkup(
    [
        ["➕ Добавить поиск", "🔎 Мои поиски"],
        ["📊 Статус", "⏸ Пауза"],
        ["▶️ Возобновить", "ℹ️ Помощь"],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Выбери действие в меню",
)

HELP_TEXT = (
    "ℹ️ Как пользоваться Avito Sniper AI\n\n"
    "➕ Добавить поиск — создай фильтр по ключевым словам.\n"
    "🔎 Мои поиски — посмотри сохранённые фильтры.\n"
    "📊 Статус — состояние бота и счётчики.\n"
    "⏸ Пауза / ▶️ Возобновить — выключить или включить фильтры.\n\n"
    "Также доступны команды: /addsearch, /searches, /status, /pause, /resume, /help.\n\n"
    "Важно: подключение к объявлениям Avito пока не реализовано. Сейчас бот сохраняет фильтры, "
    "но ещё не собирает объявления и не отправляет реальные находки."
)


def build_application(settings: Settings) -> Application:
    db = Database(settings.database_path)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        db.register_user(user.id, user.username)
        context.user_data.pop("awaiting_search", None)
        await msg.reply_text(
            "🎯 Avito Sniper AI\n\n"
            "Добро пожаловать! Управляй поисками через меню ниже.\n"
            "Пока работает сохранение фильтров; сбор объявлений Avito ещё не подключён.",
            reply_markup=MENU,
        )

    async def add_search_value(user_id: int, username: str | None, raw: str) -> str:
        db.register_user(user_id, username)
        parts = [part.strip() for part in raw.split("|")]
        if not parts[0] or len(parts[0]) > 120:
            return "Укажи запрос длиной от 1 до 120 символов."
        region = parts[1] if len(parts) > 1 and parts[1] else "Вся Россия"
        if len(region) > 80:
            return "Название региона слишком длинное."
        try:
            max_price = int(parts[2]) if len(parts) > 2 and parts[2] else None
            if max_price is not None and max_price <= 0:
                raise ValueError
        except ValueError:
            return "Максимальная цена должна быть положительным целым числом."
        search_id = db.add_search(user_id, parts[0], region, max_price)
        return (
            f"✅ Поиск №{search_id} сохранён!\n"
            f"Запрос: {parts[0]}\nРегион: {region}\n"
            f"Лимит цены: {f'{max_price:,}'.replace(',', ' ' ) + ' ₽' if max_price else 'не задан'}\n\n"
            "Обрати внимание: автоматический сбор объявлений пока не подключён."
        )

    async def addsearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, msg = update.effective_user, update.effective_message
        if not user or not msg:
            return
        raw = " ".join(context.args).strip()
        if not raw:
            context.user_data["awaiting_search"] = True
            await msg.reply_text(
                "Напиши поисковый запрос в формате:\n"
                "iPhone 15 | Вся Россия | 70000\n\n"
                "Третий параметр необязателен. Без региона используется «Вся Россия».",
                reply_markup=MENU,
            )
            return
        await msg.reply_text(await add_search_value(user.id, user.username, raw), reply_markup=MENU)

    async def searches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, msg = update.effective_user, update.effective_message
        if not user or not msg:
            return
        rows = db.list_searches(user.id)
        if not rows:
            await msg.reply_text("🔎 Пока нет сохранённых поисков. Нажми «➕ Добавить поиск».", reply_markup=MENU)
            return
        lines = ["🔎 Твои поиски:"]
        for row in rows:
            state = "🟢 активен" if row["enabled"] else "⏸ на паузе"
            price = f"до {row['max_price']:,} ₽".replace(",", " ") if row["max_price"] else "без лимита цены"
            lines.append(f"\n#{row['id']} · {row['query']}\nРегион: {row['region']} · {price}\n{state}")
        await msg.reply_text("\n".join(lines), reply_markup=MENU)

    async def set_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE, enabled: bool) -> None:
        user, msg = update.effective_user, update.effective_message
        if not user or not msg:
            return
        count = db.set_searches_enabled(user.id, enabled)
        label = "включены" if enabled else "приостановлены"
        await msg.reply_text(
            f"{'▶️' if enabled else '⏸'} Фильтры {label}. Изменено: {count}.\n"
            "Это меняет настройки, но не запускает сбор объявлений.",
            reply_markup=MENU,
        )

    async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_enabled(update, context, False)

    async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_enabled(update, context, True)

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, msg = update.effective_user, update.effective_message
        if not user or not msg:
            return
        active, alerts = db.stats(user.id)
        total = len(db.list_searches(user.id))
        await msg.reply_text(
            "📊 Статус Avito Sniper AI\n\n"
            f"Всего поисков: {total}\nАктивных фильтров: {active}\nУведомлений: {alerts}\n\n"
            "Источник Avito: не подключён\nАвтосбор объявлений: выключен\nПокупки: только вручную, по твоему решению.",
            reply_markup=MENU,
        )

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(HELP_TEXT, reply_markup=MENU)

    async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, user = update.effective_message, update.effective_user
        if not msg or not user:
            return
        value = (msg.text or "").strip()
        if context.user_data.get("awaiting_search"):
            if value == "❌ Отмена":
                context.user_data.pop("awaiting_search", None)
                await msg.reply_text("Создание поиска отменено.", reply_markup=MENU)
                return
            if value in {"➕ Добавить поиск", "🔎 Мои поиски", "📊 Статус", "⏸ Пауза", "▶️ Возобновить", "ℹ️ Помощь"}:
                context.user_data.pop("awaiting_search", None)
            else:
                context.user_data.pop("awaiting_search", None)
                await msg.reply_text(await add_search_value(user.id, user.username, value), reply_markup=MENU)
                return
        routes = {
            "➕ Добавить поиск": addsearch,
            "🔎 Мои поиски": searches,
            "📊 Статус": status,
            "⏸ Пауза": pause,
            "▶️ Возобновить": resume,
            "ℹ️ Помощь": help_command,
        }
        handler = routes.get(value)
        if handler:
            await handler(update, context)

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "Открыть главное меню"),
            BotCommand("addsearch", "Добавить поисковый фильтр"),
            BotCommand("searches", "Мои поиски"),
            BotCommand("status", "Статус бота"),
            BotCommand("pause", "Приостановить фильтры"),
            BotCommand("resume", "Возобновить фильтры"),
            BotCommand("help", "Помощь"),
        ])

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        LOG.exception("Unhandled Telegram update error", exc_info=context.error)

    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsearch", addsearch))
    app.add_handler(CommandHandler("searches", searches))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    app.add_error_handler(error_handler)
    app.bot_data["settings"] = settings
    app.bot_data["database"] = db
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    application = build_application(settings)
    LOG.info("Starting separate Avito Sniper AI Telegram bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
