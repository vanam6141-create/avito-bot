from __future__ import annotations

import logging

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .db import Database

LOG = logging.getLogger("avito_sniper_ai")
MINI_APP_URL = "https://avito-sniper-ai.onrender.com/"


def dashboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Открыть Mini App", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton("➕ Создать поиск", callback_data="add")],
        [
            InlineKeyboardButton("🔎 Мои поиски", callback_data="searches"),
            InlineKeyboardButton("📊 Статистика", callback_data="status"),
        ],
        [
            InlineKeyboardButton("⏸ Приостановить всё", callback_data="pause_all"),
            InlineKeyboardButton("▶️ Включить всё", callback_data="resume_all"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
            InlineKeyboardButton("❔ Помощь", callback_data="help"),
        ],
    ])


def build_application(settings: Settings) -> Application:
    db = Database(settings.database_path)

    async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit: bool = False) -> None:
        user = update.effective_user
        if user:
            db.register_user(user.id, user.username)
        text = (
            "🎯 <b>AVITO SNIPER AI</b>\n"
            "Управление поисками и фильтрами в одном месте.\n\n"
            "Выбери действие:\n"
            "• создай поисковый фильтр;\n"
            "• управляй сохранёнными поисками;\n"
            "• меняй параметры и смотри статистику.\n\n"
            "⚪ <b>Статус источника:</b> Avito пока не подключён"
        if edit and update.callback_query and update.callback_query.message:
            await update.callback_query.message.edit_text(
                text, reply_markup=dashboard(), parse_mode="HTML"
            )
        elif update.effective_message:
            await update.effective_message.reply_text(
                text, reply_markup=dashboard(), parse_mode="HTML"
            )

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data.pop("awaiting_search", None)
        await show_home(update, context)

    async def add_search_value(user_id: int, username: str | None, raw: str) -> str:
        db.register_user(user_id, username)
        parts = [part.strip() for part in raw.split("|")]
        query = parts[0] if parts else ""
        if not query or len(query) > 120:
            return "⚠️ Запрос должен содержать от 1 до 120 символов. Попробуй ещё раз."
        region = parts[1] if len(parts) > 1 and parts[1] else "Вся Россия"
        if len(region) > 80:
            return "⚠️ Название региона слишком длинное. Попробуй ещё раз."
        try:
            max_price = int(parts[2]) if len(parts) > 2 and parts[2] else None
            if max_price is not None and max_price <= 0:
                raise ValueError
        except ValueError:
            return "⚠️ Максимальная цена должна быть положительным числом. Попробуй ещё раз."
        search_id = db.add_search(user_id, query, region, max_price)
        price_text = f"{max_price:,}".replace(",", " ") + " ₽" if max_price else "без ограничения"
        return (
            f"✅ <b>Фильтр №{search_id} сохранён</b>\n\n"
            f"🔎 Запрос: {query}\n📍 Регион: {region}\n💰 Цена: {price_text}\n\n"
            "Фильтр сохранён. Реальный сбор объявлений Avito пока не подключён."
        )

    async def begin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data["awaiting_search"] = True
        text = (
            "➕ <b>Новый поисковый фильтр</b>\n\n"
            "Отправь запрос одной строкой в формате:\n"
            "<code>iPhone 15 | Вся Россия | 70000</code>\n\n"
            "1. Что ищем — обязательно\n"
            "2. Регион — можно оставить пустым\n"
            "3. Максимальная цена — необязательно\n\n"
            "Чтобы отменить, отправь слово «Отмена»."
        )
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode="HTML")
        elif update.effective_message:
            await update.effective_message.reply_text(text, parse_mode="HTML")

    async def show_searches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return
        rows = db.list_searches(user.id)
        if not rows:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать первый поиск", callback_data="add")],
                [InlineKeyboardButton("↩️ В главное меню", callback_data="home")],
            ])
            text = "🔎 <b>Мои поиски</b>\n\nПока здесь пусто. Создай первый фильтр — он появится в этом списке."
        else:
            buttons = []
            for row in rows:
                state = "🟢" if row["enabled"] else "⏸"
                label = f"{state} {row['query'][:28]}"
                buttons.append([InlineKeyboardButton(label, callback_data=f"search:{row['id']}")])
            buttons.append([InlineKeyboardButton("➕ Добавить ещё", callback_data="add")])
            buttons.append([InlineKeyboardButton("↩️ В главное меню", callback_data="home")])
            keyboard = InlineKeyboardMarkup(buttons)
            active = sum(1 for row in rows if row["enabled"])
            text = f"🔎 <b>Мои поиски</b>\n\nВсего фильтров: <b>{len(rows)}</b>\nАктивных: <b>{active}</b>\n\nВыбери фильтр, чтобы открыть его настройки."
        if update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    async def show_search_detail(query, user_id: int, search_id: int) -> None:
        row = db.get_search(user_id, search_id)
        if not row:
            await query.edit_message_text("Этот фильтр не найден.")
            return
        price = f"{row['max_price']:,}".replace(",", " ") + " ₽" if row["max_price"] else "не задана"
        state = "🟢 Активен" if row["enabled"] else "⏸ На паузе"
        action = "⏸ Приостановить" if row["enabled"] else "▶️ Возобновить"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(action, callback_data=f"toggle:{search_id}")],
            [InlineKeyboardButton("🗑 Удалить фильтр", callback_data=f"delete_confirm:{search_id}")],
            [InlineKeyboardButton("⬅️ К списку поисков", callback_data="searches")],
            [InlineKeyboardButton("⌂ Главное меню", callback_data="home")],
        ])
        await query.edit_message_text(
            f"🧩 <b>Фильтр №{search_id}</b>\n\n"
            f"🔎 Запрос: <b>{row['query']}</b>\n"
            f"📍 Регион: {row['region']}\n"
            f"💰 Максимальная цена: {price}\n"
            f"Состояние: {state}\n\n"
            "Изменения касаются сохранённого фильтра. Мониторинг Avito пока не работает.",
            reply_markup=keyboard, parse_mode="HTML"
        )

    async def status_text(user_id: int) -> str:
        active, alerts = db.stats(user_id)
        total = len(db.list_searches(user_id))
        return (
            "📊 <b>Статистика проекта</b>\n\n"
            f"🔎 Всего фильтров: <b>{total}</b>\n"
            f"🟢 Активных фильтров: <b>{active}</b>\n"
            f"🔔 Отправлено уведомлений: <b>{alerts}</b>\n\n"
            "🟡 Сохранение фильтров: работает\n"
            "⚪ Подключение Avito: не настроено\n"
            "⚪ Сбор объявлений: не запущен\n"
            "⚪ Анализ реальных предложений: недоступен"
        )

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ В главное меню", callback_data="home")]])
        if update.callback_query:
            await update.callback_query.message.edit_text(
                await status_text(user.id), reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            await update.effective_message.reply_text(
                await status_text(user.id), reply_markup=keyboard, parse_mode="HTML"
            )

    async def help_page(query) -> None:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ В главное меню", callback_data="home")]])
        await query.edit_message_text(
            "❔ <b>Помощь</b>\n\n"
            "➕ <b>Создать поиск</b> — сохранить ключевые слова, регион и предел цены.\n"
            "🔎 <b>Мои поиски</b> — открыть и настроить каждый фильтр.\n"
            "📊 <b>Статистика</b> — посмотреть состояние сохранённых фильтров.\n"
            "⏸ <b>Приостановить всё</b> — выключить все фильтры.\n"
            "⚙️ <b>Настройки</b> — текущие возможности и ограничения.\n\n"
            "Важно: публичные объявления Avito ещё не подключены. Бот не выдаёт демонстрационные данные за реальные находки и ничего не покупает.",
            reply_markup=keyboard, parse_mode="HTML"
        )

    async def settings_page(query) -> None:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Регион по умолчанию: вся Россия", callback_data="noop")],
            [InlineKeyboardButton("⚖️ Стратегия: Balanced", callback_data="noop")],
            [InlineKeyboardButton("🚚 Доставка: предпочтение задано", callback_data="noop")],
            [InlineKeyboardButton("↩️ В главное меню", callback_data="home")],
        ])
        await query.edit_message_text(
            "⚙️ <b>Настройки</b>\n\n"
            "Здесь показаны выбранные ориентиры проекта. Сейчас они ещё не управляют реальным поиском, поскольку источник Avito не подключён.\n\n"
            "Покупки и любые действия от твоего имени не выполняются.",
            reply_markup=keyboard, parse_mode="HTML"
        )

    async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user = update.effective_user
        if not query or not user:
            return
        await query.answer()
        data = query.data or ""
        if data == "home":
            await show_home(update, context, edit=True)
        elif data == "add":
            await begin_add(update, context)
        elif data == "searches":
            await show_searches(update, context)
        elif data == "status":
            await status(update, context)
        elif data == "help":
            await help_page(query)
        elif data == "settings":
            await settings_page(query)
        elif data == "pause_all" or data == "resume_all":
            enabled = data == "resume_all"
            count = db.set_searches_enabled(user.id, enabled)
            state = "включены" if enabled else "приостановлены"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 К моим поискам", callback_data="searches")],
                [InlineKeyboardButton("↩️ В главное меню", callback_data="home")],
            ])
            await query.edit_message_text(
                f"{'▶️' if enabled else '⏸'} <b>Фильтры {state}</b>\nИзменено: {count}.\n\nЭто меняет сохранённые настройки, но не запускает сбор объявлений.",
                reply_markup=keyboard, parse_mode="HTML"
            )
        elif data.startswith("search:"):
            await show_search_detail(query, user.id, int(data.split(":", 1)[1]))
        elif data.startswith("toggle:"):
            search_id = int(data.split(":", 1)[1])
            row = db.get_search(user.id, search_id)
            if row:
                db.set_search_enabled(user.id, search_id, not bool(row["enabled"]))
            await show_search_detail(query, user.id, search_id)
        elif data.startswith("delete_confirm:"):
            search_id = int(data.split(":", 1)[1])
            row = db.get_search(user.id, search_id)
            if not row:
                await query.edit_message_text("Фильтр уже отсутствует.")
                return
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Да, удалить", callback_data=f"delete:{search_id}"),
                    InlineKeyboardButton("Нет, назад", callback_data=f"search:{search_id}"),
                ]
            ])
            await query.edit_message_text(
                f"🗑 <b>Удалить фильтр «{row['query']}»?</b>\n\nДействие нельзя отменить.",
                reply_markup=keyboard, parse_mode="HTML"
            )
        elif data.startswith("delete:"):
            search_id = int(data.split(":", 1)[1])
            deleted = db.delete_search(user.id, search_id)
            await query.edit_message_text(
                "✅ Фильтр удалён." if deleted else "Фильтр уже отсутствует.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔎 К моим поискам", callback_data="searches")],
                    [InlineKeyboardButton("⌂ Главное меню", callback_data="home")],
                ])
            )
        elif data == "noop":
            await query.answer("Эта настройка пока демонстрационная.", show_alert=True)

    async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg, user = update.effective_message, update.effective_user
        if not msg or not user:
            return
        value = (msg.text or "").strip()
        if context.user_data.get("awaiting_search"):
            if value.lower() in {"отмена", "cancel"}:
                context.user_data.pop("awaiting_search", None)
                await msg.reply_text("Создание фильтра отменено.", reply_markup=dashboard())
                return
            result = await add_search_value(user.id, user.username, value)
            if result.startswith("⚠️"):
                await msg.reply_text(result, parse_mode="HTML")
                return
            context.user_data.pop("awaiting_search", None)
            await msg.reply_text(
                result,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔎 Открыть мои поиски", callback_data="searches")],
                    [InlineKeyboardButton("⌂ Главное меню", callback_data="home")],
                ]),
                parse_mode="HTML"
            )
            return
        await msg.reply_text("Открой панель управления командой /start.", reply_markup=dashboard())

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "Открыть панель управления"),
            BotCommand("addsearch", "Создать поисковый фильтр"),
            BotCommand("searches", "Мои поиски"),
            BotCommand("status", "Статистика"),
            BotCommand("pause", "Приостановить все фильтры"),
            BotCommand("resume", "Включить все фильтры"),
            BotCommand("help", "Помощь"),
        ])

    async def addsearch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        raw = " ".join(context.args).strip()
        if raw and update.effective_user and update.effective_message:
            result = await add_search_value(update.effective_user.id, update.effective_user.username, raw)
            await update.effective_message.reply_text(result, parse_mode="HTML")
        else:
            await begin_add(update, context)

    async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user and update.effective_message:
            count = db.set_searches_enabled(update.effective_user.id, False)
            await update.effective_message.reply_text(f"⏸ Приостановлено фильтров: {count}")

    async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user and update.effective_message:
            count = db.set_searches_enabled(update.effective_user.id, True)
            await update.effective_message.reply_text(f"▶️ Включено фильтров: {count}")

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        LOG.exception("Unhandled Telegram update error", exc_info=context.error)

    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsearch", addsearch_command))
    app.add_handler(CommandHandler("searches", show_searches))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(callback_router))
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
