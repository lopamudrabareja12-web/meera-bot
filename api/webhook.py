"""
Vercel serverless entry point: Telegram calls this URL directly (webhook mode)
for every incoming message, instead of the bot polling Telegram for updates.

Drafting logic lives in engine.py, shared with api/draft.py and bot.py.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from flask import Flask, request

from engine import generate_draft

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__)


def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)


@app.route("/api/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")

    if not chat_id or not text:
        return "ok"

    if text.startswith("/start"):
        send_message(
            chat_id,
            "Send me a rough note or topic and I'll draft it in Meera's voice.\n\n"
            "Defaults to LinkedIn format. Start your message with /newsletter to draft a "
            "newsletter instead, e.g. '/newsletter niacinamide degrades 8% after 3 months...'.",
        )
        return "ok"

    channel = "linkedin"
    note = text
    if text.startswith("/newsletter"):
        channel = "newsletter"
        note = text[len("/newsletter"):].strip()
    elif text.startswith("/linkedin"):
        channel = "linkedin"
        note = text[len("/linkedin"):].strip()

    if not note:
        send_message(chat_id, "Send the note in the same message, e.g. '/newsletter <your note>'.")
        return "ok"

    try:
        result = generate_draft(channel, note)
    except Exception as exc:
        send_message(chat_id, f"Draft generation failed: {exc}")
        return "ok"

    send_message(chat_id, result["draft"])
    return "ok"


@app.route("/api/webhook", methods=["GET"])
def health():
    return "meera-bot webhook is up"
