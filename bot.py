import os
import re
import sqlite3
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("8924239590:AAEoOmMYLyb8nM2rbcYCFqW5dDu0C7ve5HA")
DB_FILE = "raqamlar.db"

app_web = Flask(name)


@app_web.route("/")
def home():
    return "Telegram bot ishlayapti!"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            text TEXT,
            phones TEXT
        )
    """)
    conn.commit()
    conn.close()


def find_phones(text):
    pattern = r'(?:\+998|998)[\s\-()]?\d{2}[\s\-()]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
    numbers = re.findall(pattern, text)

    result = []

    for number in numbers:
        digits = re.sub(r"\D", "", number)

        if digits.startswith("998") and len(digits) == 12:
            phone = "+" + digits

            if phone not in result:
                result.append(phone)

    return result


def save_data(chat_id, text, phones):
    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        "INSERT INTO data (chat_id, text, phones) VALUES (?, ?, ?)",
        (chat_id, text, ", ".join(phones))
    )

    conn.commit()
    conn.close()


def search_data(chat_id, query):
    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute(
        "SELECT text, phones FROM data WHERE chat_id = ?",
        (chat_id,)
    ).fetchall()

    conn.close()

    words = query.lower().split()
    results = []

    for text, phones in rows:
        lower_text = text.lower()
        score = 0

        for word in words:
            if len(word) >= 2 and word in lower_text:
                score += 1

        if score:
            results.append((score, text, phones))

    results.sort(reverse=True, key=lambda x: x[0])

    return results[:10]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    if update.message.from_user and update.message.from_user.is_bot:
        return

    text = update.message.text.strip()
    chat_id = update.message.chat_id

    phones = find_phones(text)

    if phones:
        save_data(chat_id, text, phones)
        return

    results = search_data(chat_id, text)

    if not results:
        return

    answer = "🔎 <b>Topilgan raqamlar:</b>\n\n"
    shown = set()

    for score, service_text, phones_text in results:

        for phone in phones_text.split(", "):

            if phone and phone not in shown:
                shown.add(phone)

                answer += f"📞 <b>{phone}</b>\n"
                answer += f"📝 {service_text[:150]}\n\n"

    if shown:
        await update.message.reply_text(
            answer,
            parse_mode="HTML"
        )


def main():

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi")

    init_db()

    Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("🚀 BOT ISHLADI!")

    application.run_polling()


if name == "main":
    main()
