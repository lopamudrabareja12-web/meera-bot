"""
Single Flask app — Vercel's Python/Flask framework preset expects exactly
one entrypoint app, not one function per file under api/. Routes:

  GET  /              web UI (public/index.html)
  POST /api/draft      JSON API for the web UI
  POST /api/webhook    Telegram webhook (bot messages arrive here)
  GET  /api/webhook    health check

Drafting logic lives in engine.py, shared with bot.py (the local polling
bot used for dev/testing).
"""

import os

import requests
from flask import Flask, jsonify, request, send_from_directory

from engine import SCORE_THRESHOLD, generate_draft, score_note

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__, static_folder="public", static_url_path="")


TELEGRAM_MESSAGE_LIMIT = 4096


def send_telegram_message(chat_id, text):
    # Telegram rejects any message over 4096 chars outright; split rather than lose it.
    chunks = [text[i:i + TELEGRAM_MESSAGE_LIMIT] for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT)] or [""]

    for chunk in chunks:
        try:
            resp = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=15,
            )
            body = resp.json()
            if not body.get("ok"):
                print(f"[telegram] sendMessage rejected: {body}")
        except Exception as exc:
            print(f"[telegram] sendMessage failed: {exc!r}")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/draft", methods=["POST"])
def draft_endpoint():
    body = request.get_json(force=True, silent=True) or {}
    note = (body.get("note") or "").strip()
    channel = body.get("channel") or "linkedin"

    if not note:
        return jsonify({"error": "note is required"}), 400

    try:
        result = generate_draft(channel, note)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)


@app.route("/api/webhook", methods=["GET"])
def webhook_health():
    return "meera-bot webhook is up"


@app.route("/api/webhook", methods=["POST"])
def webhook_endpoint():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")

    if not chat_id or not text:
        return "ok"

    if text.startswith("/start"):
        send_telegram_message(
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
        send_telegram_message(chat_id, "Send the note in the same message, e.g. '/newsletter <your note>'.")
        return "ok"

    scoring = score_note(note)
    if scoring["score"] < SCORE_THRESHOLD:
        send_telegram_message(
            chat_id,
            f"No draft made (score: {scoring['score']}/10). {scoring['reason']}",
        )
        return "ok"

    try:
        result = generate_draft(channel, note)
    except Exception as exc:
        send_telegram_message(chat_id, f"Draft generation failed: {exc}")
        return "ok"

    send_telegram_message(chat_id, result["draft"])
    return "ok"
