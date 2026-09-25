"""
Telegram bot that drafts LinkedIn posts / newsletters in Meera Pillai's voice.

Send it a rough note or topic; it replies with a draft using the Gemini API,
guided by the voice rubric in voice_rubric.py.

Commands:
  /start      - intro
  /linkedin   - draft the next message as a LinkedIn post
  /newsletter - draft the next message as a newsletter
"""

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

from engine import GEMINI_MODEL, SCORE_THRESHOLD, generate_draft, score_note  # noqa: E402

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Per-chat pending channel selection (in-memory; resets on restart)
pending_channel: dict[int, str] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me a rough note, topic, or fragment and I'll draft it in Meera's voice.\n\n"
        "Defaults to LinkedIn format. Use /newsletter before your message to draft a "
        "newsletter instead, or /linkedin to switch back."
    )


async def set_linkedin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending_channel[update.effective_chat.id] = "linkedin"
    await update.message.reply_text("Next draft will be LinkedIn format.")


async def set_newsletter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending_channel[update.effective_chat.id] = "newsletter"
    await update.message.reply_text("Next draft will be newsletter format.")


async def draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    note = update.message.text
    channel = pending_channel.get(chat_id, "linkedin")

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    scoring = score_note(note)
    if scoring["score"] < SCORE_THRESHOLD:
        await update.message.reply_text(f"No draft made (score: {scoring['score']}/10). {scoring['reason']}")
        return

    try:
        result = generate_draft(channel, note)
    except Exception:
        logger.exception("Gemini API call failed")
        await update.message.reply_text(
            "Draft generation failed — check the logs (likely an API key or rate-limit issue)."
        )
        return

    await update.message.reply_text(f"Score: {scoring['score']}/10\n\n{result['draft']}")


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("linkedin", set_linkedin))
    app.add_handler(CommandHandler("newsletter", set_newsletter))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, draft))

    logger.info("Bot starting (model=%s)...", GEMINI_MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
