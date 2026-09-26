import os
import re
import threading
from datetime import datetime, timezone

import psycopg2
from psycopg2 import pool
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

MY_SERVICES = [
    "konditsioner", "konditsaner", "kanditsioner", "кондиционер",
    "katyol", "katel", "kotel", "qozon", "gaz qozon",
    "vaillant", "vailant", "valiant", "vaylant", "вайлант",
    "котел", "котёл", "қозон",
    "santexnik", "santexnika", "сантехник", "сантехника",
    "televizor", "televizor usta", "телевизор",
    "perforator", "perforatorchi", "perfaratorchi", "перфоратор",
    "kir mashina", "kir mashinasi", "kir yuvish mashinasi",
    "kirmashina", "kirmoshina", "stiralka",
    "стиралка", "стиральная машина", "кир ювиш машинаси",
]

CATEGORY_KEYWORDS = {
    "Aptekalar": [
        "apteka", "aptekalar", "aptekasi",
        "dorixona", "dori", "dori-darmon",
        "аптека", "аптек", "дорихона"
    ],
    "Choyxonalar": [
        "choyxona", "choyxonasi", "choyxonalar",
        "malina choy", "choy", "oshxona",
        "restoran", "kafe", "kabob"
    ],
    "Konditsioner": [
        "konditsioner", "konditsaner",
        "kanditsioner", "кондиционер"
    ],
    "Katyol": [
        "katyol", "katel", "kotel", "qozon",
        "gaz qozon", "vaillant", "vailant",
        "valiant", "vaylant", "вайлант",
        "котел", "котёл", "қозон"
    ],
    "Santexnika": [
        "santexnik", "santexnika",
        "сантехник", "сантехника"
    ],
    "Televizor": [
        "televizor", "телевизор"
    ],
    "Perforator": [
        "perforator", "perforatorchi",
        "перфоратор", "перфораторчи"
    ],
    "Kir mashina": [
        "kir mashina", "kir mashinasi",
        "kir yuvish mashinasi",
        "kirmashina", "kirmoshina",
        "stiralka", "стиралка",
        "стиральная машина",
        "кир ювиш машинаси"
    ],
}

SEARCH_STOP_WORDS = [
    "nomeri", "nomer", "raqami", "raqam",
    "telefon", "telefon raqami", "telefon nomeri",
    "telefonini", "nomerini", "raqamini",
    "bormi", "bor", "kerak", "kerakmi",
    "bering", "ber", "topib ber", "topib bering",
    "qayerda", "qaysi", "kimda", "kimning",
    "menga", "iltimos", "usta", "ustasi",
    "xizmati", "xizmat"
]

PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+?998[\s\-]?)?"
    r"(?:\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})"
    r"(?!\d)"
)

# =========================================================
# DATABASE
# =========================================================

DB_POOL = None


def init_db():
    global DB_POOL

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi!")

    DB_POOL = psycopg2.pool.ThreadedConnectionPool(
        1,
        5,
        DATABASE_URL
    )

    conn = DB_POOL.getconn()

    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id BIGSERIAL PRIMARY KEY,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                source_text TEXT,
                chat_id BIGINT,
                user_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS unique_record
            ON records(category, name, phone)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_category
            ON records(category)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_phone
            ON records(phone)
        """)

        conn.commit()

        print("SUPABASE DATABASE ULANDI")

    finally:
        DB_POOL.putconn(conn)


# =========================================================
# YORDAMCHI FUNKSIYALAR
# =========================================================

def normalize(text):
    if not text:
        return ""

    text = text.lower()

    text = text.replace("’", "'")
    text = text.replace("‘", "'")
    text = text.replace("ʻ", "'")
    text = text.replace("ʼ", "'")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("998") and len(digits) == 12:
        return "+" + digits

    if len(digits) == 9:
        return "+998" + digits

    return phone.strip()


def find_phones(text):
    if not text:
        return []

    result = []

    for phone in PHONE_RE.findall(text):

        phone = normalize_phone(phone)

        if phone not in result:
            result.append(phone)

    return result


def is_my_phone(phone):
    return normalize_phone(phone) in MY_PHONES


def is_special_service(text):
    text_n = normalize(text)

    for word in MY_SERVICES:

        if normalize(word) in text_n:
            return True

    return False


def detect_category(text):
    text_n = normalize(text)

    for category, keywords in CATEGORY_KEYWORDS.items():

        for keyword in keywords:

            if normalize(keyword) in text_n:
                return category

    return None


def auto_category(text):
    category = detect_category(text)

    if category:
        return category

    text_n = normalize(text)

    for word in SEARCH_STOP_WORDS:
        text_n = text_n.replace(
            normalize(word),
            " "
        )

    for phone in find_phones(text):
        text_n = text_n.replace(phone, " ")

    text_n = re.sub(
        r"[^\w\s'-]",
        " ",
        text_n
    )

    text_n = re.sub(
        r"\s+",
        " ",
        text_n
    ).strip()

    if not text_n:
        return "Boshqa"

    words = text_n.split()[:4]

    return " ".join(words).title()


def extract_name(text, phone):

    clean = text.replace(phone, " ")

    clean = re.sub(
        r"\+?998[\d\s\-]{9,15}",
        " ",
        clean
    )

    clean = re.sub(
        r"\s+",
        " ",
        clean
    ).strip()

    clean = clean.strip(
        " -:|•📞☎️"
    )

    if not clean:
        return "Nomsiz"

    return clean[:150]


def parse_records(text):
    lines = text.splitlines()
    records = []
    current_name = None

    category = detect_category(text) or "Boshqa"

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # Umumiy sarlavhalarni nom sifatida olmaslik
        clean_line = line.strip("🏷📂📞☎️:.- ")

        if normalize(clean_line) in [
            "apteka",
            "aptekalar",
            "dorixona",
            "choyxona",
            "choyxonalar",
            "malina choy"
        ]:
            continue

        phones = find_phones(line)

        if phones:
            for phone in phones:
                records.append({
                    "category": category,
                    "name": current_name or "Nomsiz",
                    "phone": phone
                })
            continue

        # Telefon bo'lmagan qator — yangi nom
        current_name = clean_line

    return records

# =========================================================
# ADMIN TEKSHIRISH
# =========================================================

async def is_group_admin(update, context):

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return False

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
        )

        return member.status in (
            "administrator",
            "creator"
        )

    except Exception as e:

        print(
            "Admin tekshirish xatosi:",
            e
        )

        return False


# =========================================================
# SAQLASH
# =========================================================

def save_record(
    category,
    name,
    phone,
    source_text,
    chat_id,
    user_id
):

    if is_my_phone(phone):
        return False

    conn = DB_POOL.getconn()

    try:

        cur = conn.cursor()

        cur.execute("""
            INSERT INTO records
            (
                category,
                name,
                phone,
                source_text,
                chat_id,
                user_id,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (category, name, phone)
            DO NOTHING
        """, (
            category,
            name,
            normalize_phone(phone),
            source_text,
            chat_id,
            user_id,
            datetime.now(timezone.utc)
        ))

        inserted = cur.rowcount == 1

        conn.commit()

        return inserted

    finally:

        DB_POOL.putconn(conn)


# =========================================================
# QIDIRUV
# =========================================================

def clean_search_query(query):

    text = normalize(query)

    for word in sorted(
        SEARCH_STOP_WORDS,
        key=len,
        reverse=True
    ):

        text = text.replace(
            normalize(word),
            " "
        )

    text = re.sub(
        r"[^\w\s'-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def search_category(category):

    conn = DB_POOL.getconn()

    try:

        cur = conn.cursor()

        cur.execute("""
            SELECT category, name, phone
            FROM records
            WHERE LOWER(category) = LOWER(%s)
            ORDER BY name
            LIMIT 500
        """, (category,))

        return cur.fetchall()

    finally:

        DB_POOL.putconn(conn)


def search_records(query):

    cleaned = clean_search_query(query)

    if not cleaned:
        return []

    conn = DB_POOL.getconn()

    try:

        cur = conn.cursor()

        like = "%" + cleaned + "%"

        cur.execute("""
            SELECT category, name, phone
            FROM records
            WHERE
                LOWER(category) LIKE LOWER(%s)
                OR LOWER(name) LIKE LOWER(%s)
                OR LOWER(source_text) LIKE LOWER(%s)
            ORDER BY category, name
            LIMIT 500
        """, (
            like,
            like,
            like
        ))

        rows = cur.fetchall()

        if rows:
            return rows

        # Alohida so'zlar bo'yicha
        result = []
        seen = set()

        for word in cleaned.split():

            if len(word) < 2:
                continue

            like_word = "%" + word + "%"

            cur.execute("""
                SELECT category, name, phone
                FROM records
                WHERE
                    LOWER(category) LIKE LOWER(%s)
                    OR LOWER(name) LIKE LOWER(%s)
                    OR LOWER(source_text) LIKE LOWER(%s)
                ORDER BY category, name
                LIMIT 500
            """, (
                like_word,
                like_word,
                like_word
            ))

            for row in cur.fetchall():

                key = (
                    row[0],
                    row[1],
                    row[2]
                )

                if key not in seen:

                    seen.add(key)
                    result.append(row)

        return result

    finally:

        DB_POOL.putconn(conn)


# =========================================================
# NATIJA
# =========================================================

async def send_long_result(update, rows):

    if not rows:
        return

    lines = []

    for category, name, phone in rows:

        lines.append(
            f"📂 {category}\n"
            f"🏷 {name}\n"
            f"📞 {phone}"
        )

    text = "\n\n".join(lines)

    while text:

        if len(text) <= 3500:

            await update.message.reply_text(text)

            break

        cut = text.rfind(
            "\n",
            0,
            3500
        )

        if cut == -1:
            cut = 3500

        await update.message.reply_text(
            text[:cut]
        )

        text = text[cut:].lstrip()


async def send_my_services(update):

    await update.message.reply_text(
        "+998979600501\n"
        "+998911517577"
    )


# =========================================================
# ASOSIY HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    if (
        message.from_user
        and message.from_user.is_bot
    ):
        return

    text = (
        message.text
        or message.caption
        or ""
    )

    if not text:
        return

    # Reply xabarni ham ko'radi
    if message.reply_to_message:

        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

        if reply_text:

            text = (
                reply_text
                + "\n"
                + text
            )

    special = is_special_service(text)

    phones = find_phones(text)

    # -----------------------------------------------------
    # MAXSUS XIZMAT
    # -----------------------------------------------------

    if special:

        # Maxsus xizmatlarda
        # boshqa raqamlar SAQLANMAYDI.

        if not phones:

            await send_my_services(update)

        else:

            await send_my_services(update)

        return

    # -----------------------------------------------------
    # RAQAM YO'Q → QIDIRUV
    # -----------------------------------------------------

    if not phones:

        category = detect_category(text)

        if category:

            rows = search_category(
                category
            )

        else:

            rows = search_records(
                text
            )

        if not rows:
            return

        await send_long_result(
            update,
            rows
        )

        return

    # -----------------------------------------------------
    # RAQAM BOR → FAQAT ADMIN
    # -----------------------------------------------------

    admin = await is_group_admin(
        update,
        context
    )

    if not admin:

        return

    records = parse_records(text)

    for record in records:

        save_record(
            category=record["category"],
            name=record["name"],
            phone=record["phone"],
            source_text=text,
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )

    # Admin xabariga javob bermaydi.


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram bot ishlayapti."


@app.route("/health")
def health():
    return "OK"


def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi!"
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL topilmadi!"
        )

    # PostgreSQL ulanishi
    init_db()

    # Render health server
    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.ALL,
            handle_message
        )
    )

    print(
        "PRO BOT + SUPABASE ISHLADI..."
    )

    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
