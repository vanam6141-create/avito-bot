from __future__ import annotations

import logging
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import Settings
from .db import Database

LOG = logging.getLogger("avito_sniper_ai")
QUERY_RE = re.compile(r"^/addsearch\\s+(.+)$", re.IGNORECASE | re.DOTALL)


def build_application(settings: Settings) -> Application:
    db = Database(settings.database_path)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.effective_message:
            return
        db.register_user(user.id, user.username)
        await update.effective_message.reply_text(
            "🎯 Avito Sniper AI\n\n"
            "Отдельный бот мониторинга. Пока подключены настройки и база данных; "
            "источник объявлений ещё не активирован.\n\n"
            "Команды:\n"
            "/addsearch запрос | регион | макс_цена\n"
            "/searches — мои фильтры\n"
            "/pause — приостановить фильтры\n"
            "/resume — включить фильтры\n"
            "/status — состояние"
        )

    async def addsearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        db.register_user(user.id, user.username)
        raw = msg.text or ""
        match = QUERY_RE.match(raw)
        if not match:
            await msg.reply_text("Формат: /addsearch MacBook Air | Вся Россия | 80000")
            return
        parts = [part.strip() for part in match.group(1).split("|")]
        if not parts[0] or len(parts[0]) > 120:
            await msg.reply_text("Запрос должен содержать от 1 до 120 символов.")
            return
        region = parts[1] if len(parts) > 1 and parts[1] else "Вся Россия"
        if len(region) > 80:
            await msg.reply_text("Название региона слишком длинное.")
            return
        try:
            max_price = int(parts[2]) if len(parts) > 2 and parts[2] else None
            if max_price is not None and max_price <= 0:
                raise ValueError
        except ValueError:
            await msg.reply_text("Максимальная цена должна быть положительным целым числом.")
            return
        search_id = db.add_search(user.id, parts[0], region, max_price)
        await msg.reply_text(f"Фильтр №{search_id} сохранён. Реальный сбор объявлений пока не включён.")

    async def searches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        rows = db.list_searches(user.id)
        if not rows:
            await msg.reply_text("Фильтров пока нет. Добавь: /addsearch запрос | регион | макс_цена")
            return
        lines = ["🔎 Твои фильтры:"]
        for row in rows:
            state = "включён" if row["enabled"] else "пауза"
            price = f"до {row['max_price']} ₽" if row["max_price"] else "без лимита цены"
            lines.append(f"#{row['id']} · {row['query']} · {row['region']} · {price} · {state}")
        await msg.reply_text("\\n".join(lines))

    async def set_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE, enabled: bool) -> None:
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        count = db.set_searches_enabled(user.id, enabled)
        await msg.reply_text(f"Обновлено фильтров: {count}. Это меняет настройки, но не запускает сбор объявлений.")

    async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_enabled(update, context, False)

    async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await set_enabled(update, context, True)

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        active, alerts = db.stats(user.id)
        await msg.reply_text(
            f"Состояние Sniper AI\\nАктивных фильтров: {active}\\nУведомлений: {alerts}\\n"
            "Источник Avito: не подключён. Покупки бот не совершает."
        )

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        LOG.exception("Unhandled Telegram update error", exc_info=context.error)

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addsearch", addsearch))
    app.add_handler(CommandHandler("searches", searches))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("status", status))
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
