import os
import re
import sqlite3
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("8924239590:AAEoOmMYLyb8nM2rbcYCFqW5dDu0C7ve5HA")
DB_FILE = "raqamlar.db"


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
        digits = re.sub(r'\D', '', number)

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

    query_words = query.lower().split()
    results = []

    for text, phones in rows:
        text_lower = text.lower()
        score = 0

        for word in query_words:
            if len(word) >= 2 and word in text_lower:
                score += 1

        if score > 0:
            results.append((score, text, phones))

    results.sort(reverse=True, key=lambda x: x[0])

    return results[:10]


async def handle_message(update: Update, context: ContextTypes.DEFAULT