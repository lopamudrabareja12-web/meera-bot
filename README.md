# meera-bot

Drafts LinkedIn posts / newsletters in Meera Pillai's (Skinstinct) writing
voice — sourced number, mechanism before conclusion, self-interest
disclaimer, verify-don't-pitch ending — grounded with a real, relevant
Google News link when one exists.

## Layout

```
engine.py          shared drafting logic (Gemini + voice rubric + news pick)
voice_rubric.py     the system prompt distilled from the voice analysis
news.py             Google News RSS lookup + relevance selection

bot.py               local Telegram bot (polling) — for dev/testing
api/webhook.py       Telegram bot (webhook) — Vercel production entry point
api/draft.py         JSON API for the web UI — Vercel production entry point
public/index.html    small web UI, posts to /api/draft, renders on page
```

`bot.py` and the `api/` functions all call into `engine.py` — one
implementation, three entry points.

## Local dev

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
./venv/bin/python bot.py
```

## Production (Vercel)

Deployed from this repo via the Vercel CLI, with `TELEGRAM_BOT_TOKEN`,
`GEMINI_API_KEY`, and `GEMINI_MODEL` set as environment variables in the
Vercel project (Production + Preview). After a deploy, the Telegram
webhook is pointed at `https://<deployment-url>/api/webhook` — only one
of `bot.py` (polling) or the webhook should be active for a given bot
token at a time, since Telegram allows only one update-delivery mode per
bot.
