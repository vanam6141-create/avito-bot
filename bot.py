"""New Avito Sniper AI entry point.

The old review-task bot is no longer started; its previous version remains in
Git history. A tiny HTTP health endpoint is retained for Render Web Services.
"""
import os
from threading import Thread
from flask import Flask
from sniper_ai.bot import main as run_sniper

health_app = Flask(__name__)

@health_app.get("/health")
def health():
    return {"status": "ok", "service": "avito-sniper-ai"}, 200

def run_health_server():
    health_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), use_reloader=False)

if __name__ == "__main__":
    Thread(target=run_health_server, daemon=True, name="health-server").start()
    run_sniper()
