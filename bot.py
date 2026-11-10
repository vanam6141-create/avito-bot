"""Avito Sniper AI: Telegram bot and authenticated Mini App API."""
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
from telegram.ext import Application

from sniper_ai.bot import main as run_sniper
from sniper_ai.config import Settings
from sniper_ai.db import Database

logging.getLogger("httpx").setLevel(logging.WARNING)
health_app = Flask(__name__)
settings = Settings.from_env()
db = Database(settings.database_path)
WEB_DIR = Path(__file__).resolve().parent


def telegram_user():
    """Validate Telegram Mini App initData before trusting its user id."""
    raw = request.headers.get("X-Telegram-Init-Data", "")
    if not raw or len(raw) > 8192:
        return None
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
        received_hash = pairs.pop("hash", "")
        auth_date = int(pairs.get("auth_date", "0"))
        if not received_hash or abs(int(time.time()) - auth_date) > 86400:
            return None
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None
        user = json.loads(pairs["user"])
        user_id = int(user["id"])
        db.register_user(user_id, user.get("username"))
        return user_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def require_user():
    user_id = telegram_user()
    if user_id is None:
        return None, (jsonify({"error": "Telegram authentication required"}), 401)
    return user_id, None


@health_app.get("/")
def mini_app():
    return send_from_directory(WEB_DIR, "index.html")


@health_app.get("/health")
def health():
    return {"status": "ok", "service": "avito-sniper-ai"}, 200


@health_app.get("/api/searches")
def api_list_searches():
    user_id, error = require_user()
    if error:
        return error
    rows = db.list_searches(user_id)
    return jsonify([{
        "id": row["id"], "query": row["query"], "region": row["region"],
        "max_price": row["max_price"], "enabled": bool(row["enabled"])
    } for row in rows])


@health_app.post("/api/searches")
def api_add_search():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    region = str(payload.get("region", "Вся Россия")).strip() or "Вся Россия"
    raw_price = payload.get("max_price")
    if not query or len(query) > 120 or len(region) > 80:
        return jsonify({"error": "Проверь запрос и регион"}), 400
    try:
        max_price = int(raw_price) if raw_price not in (None, "") else None
        if max_price is not None and max_price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Цена должна быть положительным числом"}), 400
    search_id = db.add_search(user_id, query, region, max_price)
    return jsonify({"id": search_id, "ok": True}), 201


@health_app.patch("/api/searches/<int:search_id>")
def api_update_search(search_id):
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("enabled"), bool):
        return jsonify({"error": "Ожидается enabled: true или false"}), 400
    if not db.set_search_enabled(user_id, search_id, payload["enabled"]):
        return jsonify({"error": "Фильтр не найден"}), 404
    return jsonify({"ok": True})


@health_app.delete("/api/searches/<int:search_id>")
def api_delete_search(search_id):
    user_id, error = require_user()
    if error:
        return error
    if not db.delete_search(user_id, search_id):
        return jsonify({"error": "Фильтр не найден"}), 404
    return jsonify({"ok": True})


@health_app.get("/api/products")
def api_products():
    user_id, error = require_user()
    if error:
        return error
    return jsonify(db.list_tracked_products(user_id))


@health_app.get("/api/products/<int:product_id>/history")
def api_product_history(product_id):
    user_id, error = require_user()
    if error:
        return error
    if not db.get_tracked_product(user_id, product_id):
        return jsonify({"error": "Товар не найден"}), 404
    return jsonify(db.list_product_history(user_id, product_id))


@health_app.get("/api/settings")
def api_get_settings():
    user_id, error = require_user()
    if error:
        return error
    return jsonify(db.get_settings(user_id))


@health_app.put("/api/settings")
def api_put_settings():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        min_score = int(payload.get("min_score", 70))
        categories = payload.get("categories", [])
        if not 0 <= min_score <= 100 or not isinstance(categories, list) or len(categories) > 40:
            raise ValueError
        categories = [str(item)[:60] for item in categories if isinstance(item, str)]
    except (TypeError, ValueError):
        return jsonify({"error": "Некорректные настройки"}), 400
    db.set_settings(user_id, min_score=min_score, categories=categories)
    return jsonify({"ok": True})


def run_health_server():
    health_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), use_reloader=False)


if __name__ == "__main__":
    Thread(target=run_health_server, daemon=True, name="health-server").start()
    run_sniper()
