"""
Vercel serverless entry point for the web UI (public/index.html).
Same drafting engine as the Telegram webhook, exposed as a small JSON API.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request

from engine import generate_draft

app = Flask(__name__)


@app.route("/api/draft", methods=["POST"])
def draft():
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
