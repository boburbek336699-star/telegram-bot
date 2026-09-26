import os
import re
import sqlite3
import threading
from datetime import datetime

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Render Environment Variables ni tekshiring."
    )

DB_FILE = "bot_database.db"

MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

# =========================================================
# MAXSUS XIZMATLAR
# =========================================================
# =========================================================
# KATEGORIYALAR
# =========================================================

CATEGORY_KEYWORDS = {
    "Choyxonalar": [
        "choyxona",
        "choyxonasi",
        "choyxonalar",
        "malina choy",
        "choy",
        "oshxona",
        "restoran",
        "kafe",
        "kabob",
        "soy choyxona",
    ],

    "Aptekalar": [
        "apteka",
        "aptekalar",
        "aptekasi",
        "dorixona",
        "dori-darmon",
        "аптека",
        "аптек",
        "дорихона",
    ],
}

# =========================================================
# REKLAMA ANIQLASH
# =========================================================

AD_WORDS = [
    "universal master",
    "murojaat uchun",
    "xizmat ko'rsatamiz",
    "xizmat korsatamiz",
    "xizmatlarimiz",
    "sifatli xizmat",
    "tezkor xizmat",
    "hamyonbop narx",
    "arzon narx",
    "kafolat bilan",
    "uyga borib xizmat",
    "mijozlar uchun",
    "buyurtma uchun",
]

SERVICE_WORDS = [
    "elektrik",
    "svarka",
    "gaz montaj",
    "suv montaj",
    "lyustra",
    "plafon",
    "antenna",
    "nasos",
    "o'rnatish",
    "ornatish",
    "ta'mirlash",
    "tamirlash",
]

# =========================================================
# DATABASE
# =========================================================

DB_LOCK = threading.Lock()


def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def create_database():
    with DB_LOCK:
        conn = get_db()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                source_text TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS unique_record
            ON records(category, name, phone)
        """)

        conn.commit()
        conn.close()


# =========================================================
# TEXT
# =========================================================

def normalize(text):
    if not text:
        return ""

    text = text.lower()

    replacements = {
        "ё": "е",
        "ў": "у",
        "ғ": "г",
        "қ": "к",
        "ҳ": "х",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# PHONE
# =========================================================

PHONE_RE = re.compile(
    r"""
    (?<!\d)
    (?:\+?998)
    [\s\-()]*
    \d{2}
    [\s\-()]*
    \d{3}
    [\s\-()]*
    \d{2}
    [\s\-()]*
    \d{2}
    (?!\d)
    """,
    re.VERBOSE,
)


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

    found = []

    for match in PHONE_RE.findall(text):
        phone = normalize_phone(match)

        if phone not in found:
            found.append(phone)

    return found


# =========================================================
# NOISE
# =========================================================

def clean_line(line):
    line = line.strip()

    line = re.sub(
        r"^[\s\-–—•▪️🔹🔸📞☎️📱👉🏻👉🏼👉🏽👉🏾👉🏿\d.)]+",
        "",
        line,
    )

    return line.strip(" -–—:|")


def meaningful_line(line):
    if not line:
        return False

    n = normalize(line)

    noise = [
        "kerakli raqam",
        "kerakli nomer",
        "telefon",
        "tel",
        "nomer",
        "raqam",
    ]

    if n in noise:
        return False

    if len(n) < 2:
        return False

    return True


# =========================================================
# MAXSUS XIZMAT
# =========================================================

def is_my_service(text):
    n = normalize(text)

    for service in MY_SERVICES:
        if normalize(service) in n:
            return True

    return False


# =========================================================
# CATEGORY
# =========================================================

def detect_category(text):
    n = normalize(text)

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if normalize(keyword) in n:
                return category

    return "Boshqa"


# =========================================================
# REKLAMA
# =========================================================

def is_advertisement(text):
    n = normalize(text)

    ad_score = 0

    for word in AD_WORDS:
        if normalize(word) in n:
            ad_score += 2

    service_count = 0

    for word in SERVICE_WORDS:
        if normalize(word) in n:
            service_count += 1

    if service_count >= 3:
        ad_score += 3

    if "universal master" in n:
        return True

    return ad_score >= 4


# =========================================================
# NAME / PHONE PARSER
# =========================================================

def parse_records(text):
    """
    Xabarni qatorma-qator o'qiydi.

    Misol:

    MALINA CHOY
    +998335999595 Navoiy
    +998903629595
    +998999229595 Charxiy

    Natija:

    MALINA CHOY — Navoiy
    MALINA CHOY
    MALINA CHOY — Charxiy
    """

    if not text:
        return []

    lines = text.splitlines()

    results = []

    current_name = ""

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        phones = find_phones(line)

        if phones:

            # Telefonlarni olib tashlab, qolgan matnni nom sifatida olamiz
            label = PHONE_RE.sub("", line)

            label = clean_line(label)

            if label:
                if current_name:
                    # Masalan:
                    # MALINA CHOY +998... Navoiy
                    # => MALINA CHOY — Navoiy

                    if normalize(label) not in normalize(current_name):
                        name = f"{current_name} — {label}"
                    else:
                        name = current_name
                else:
                    name = label
            else:
                name = current_name

            if not name:
                name = "Nomi ko'rsatilmagan"

            for phone in phones:
                results.append({
                    "name": name,
                    "phone": phone,
                })

        else:

            cleaned = clean_line(line)

            if meaningful_line(cleaned):

                # Keraksiz sarlavhalarni nom sifatida saqlamaymiz
                if normalize(cleaned) not in [
                    "aptekalar",
                    "choyxonalar",
                    "kerakli raqam",
                ]:
                    current_name = cleaned

    return results


# =========================================================
# SAVE
# =========================================================

def save_record(chat_id, category, name, phone, source_text):

    with DB_LOCK:

        conn = get_db()

        cursor = conn.execute(
            """
            SELECT id
            FROM records
            WHERE category = ?
            AND name = ?
            AND phone = ?
            """,
            (
                category,
                name,
                phone,
            ),
        )

        exists = cursor.fetchone()

        if exists:
            conn.close()

            print(
                f"♻️ OLDIN BOR: {category} | {name} | {phone}"
            )

            return False

        conn.execute(
            """
            INSERT INTO records
            (
                chat_id,
                category,
                name,
                phone,
                source_text,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                category,
                name,
                phone,
                source_text,
                datetime.now().isoformat(),
            ),
        )

        conn.commit()
        conn.close()

    print(
        f"💾 SAQLANDI: {category} | {name} | {phone}"
    )

    return True


# =========================================================
# SEARCH
# =========================================================

def search_records(query, limit=30):

    q = normalize(query)

    if not q:
        return []

    with DB_LOCK:

        conn = get_db()

        rows = conn.execute(
            """
            SELECT *
            FROM records
            WHERE
                lower(name) LIKE ?
                OR lower(phone) LIKE ?
                OR lower(category) LIKE ?
            ORDER BY
                category,
                name
            LIMIT ?
            """,
            (
                f"%{q}%",
                f"%{q}%",
                f"%{q}%",
                limit,
            ),
        ).fetchall()

        conn.close()

    return rows


def search_category(category, limit=50):

    with DB_LOCK:

        conn = get_db()

        rows = conn.execute(
            """
            SELECT *
            FROM records
            WHERE category = ?
            ORDER BY name, phone
            LIMIT ?
            """,
            (
                category,
                limit,
            ),
        ).fetchall()

        conn.close()

    return rows


# =========================================================
# FORMAT SEARCH RESULT
# =========================================================

def format_results(rows):

    if not rows:
        return "❌ Ma'lumot topilmadi."

    grouped = {}

    for row in rows:

        key = (
            row["category"],
            row["name"],
        )

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(row["phone"])

    output = []

    for (category, name), phones in grouped.items():

        output.append(
            f"🏷 {category}\n"
            f"📍 {name}"
        )

        for phone in phones:
            output.append(
                f"📞 {phone}"
            )

        output.append("")

    text = "\n".join(output)

    return text[:3900]


# =========================================================
# MAXSUS XIZMAT JAVOBI
# =========================================================

async def send_my_service(update):

    text = (
        "📞 KERAKLI RAQAM\n\n"
        f"1️⃣ {MY_PHONES[0]}\n"
        f"2️⃣ {MY_PHONES[1]}"
    )

    await update.message.reply_text(text)


# =========================================================
# /START
# =========================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🤖 PRO KERAKLI RAQAMLAR BOT\n\n"
        "Kerakli xizmat yoki nomni yozing.\n\n"
        "Masalan:\n"
        "🔎 apteka\n"
        "🔎 choyxona\n"
        "🔎 Romanka\n"
        "🔎 Malina choy\n\n"
        "📥 Guruhdagi yangi raqamlar avtomatik bazaga yig'iladi."
    )


# =========================================================
# /STATS
# =========================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    with DB_LOCK:

        conn = get_db()

        total = conn.execute(
            "SELECT COUNT(*) FROM records"
        ).fetchone()[0]

        categories = conn.execute(
            """
            SELECT category, COUNT(*)
            FROM records
            GROUP BY category
            ORDER BY category
            """
        ).fetchall()

        conn.close()

    lines = [
        "📊 BOT BAZASI",
        "",
        f"📞 Jami raqamlar: {total}",
        "",
    ]

    for row in categories:

        lines.append(
            f"• {row[0]}: {row[1]}"
        )

    await update.message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# /SEARCH
# =========================================================

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = " ".join(context.args).strip()

    if not query:

        await update.message.reply_text(
            "🔎 Masalan:\n"
            "/search apteka\n"
            "/search Romanka\n"
            "/search Malina choy"
        )

        return

    rows = search_records(query)

    await update.message.reply_text(
        format_results(rows)
    )


# =========================================================
# MAIN MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # Bot o'z xabarini qayta saqlamasin
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""

    if not text:
        return

    # =====================================================
    # DEBUG
    # =====================================================

    print(
        "\n=============================="
    )

    print(
        "📥 YANGI XABAR:"
    )

    print(
        text[:1500]
    )

    # =====================================================
    # REPLY XABAR
    # =====================================================

    # Agar joriy xabarda telefon bo'lmasa,
    # reply qilingan xabarni ham tekshiramiz.

    phones_current = find_phones(text)

    reply_text = ""

    if (
        not phones_current
        and message.reply_to_message
    ):

        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

    parse_text = text

    if reply_text:
        parse_text = reply_text

    # =====================================================
    # MAXSUS XIZMAT
    # =====================================================

    if is_my_service(text):

        await send_my_service(update)

        print(
            "⭐ MAXSUS XIZMAT — tashqi raqam saqlanmadi"
        )

        return

    # =====================================================
    # PHONES
    # =====================================================

    phones = find_phones(parse_text)

    print(
        f"📞 TOPILGAN RAQAMLAR: {phones}"
    )

    # =====================================================
    # AGAR RAQAM BO'LMASA — QIDIRUV
    # =====================================================

    if not phones:

        # Kategoriya bo'yicha
        category = detect_category(text)

        if category != "Boshqa":

            rows = search_category(
                category,
                50
            )

            if rows:

                await update.message.reply_text(
                    format_results(rows)
                )

                return

        # Oddiy nom bo'yicha
        rows = search_records(
            text,
            30
        )

        if rows:

            await update.message.reply_text(
                format_results(rows)
            )

        else:

            await update.message.reply_text(
                "❌ Bunday ma'lumot bazada topilmadi."
            )

        return

    # =====================================================
    # REKLAMA BO'LSA — SAQLAMAYMIZ
    # =====================================================

    if is_advertisement(parse_text):

        print(
            "🚫 REKLAMA — bazaga saqlanmadi"
        )

        return

    # =====================================================
    # CATEGORY
    # =====================================================

    category = detect_category(parse_text)

    # =====================================================
    # PARSE
    # =====================================================

    parsed = parse_records(parse_text)

    # Agar parser nom chiqarmagan bo'lsa
    # umumiy nomdan foydalanamiz.

    if not parsed:

        for phone in phones:

            parsed.append({
                "name": "Nomi ko'rsatilmagan",
                "phone": phone,
            })

    # =====================================================
    # SAVE
    # =====================================================

    saved_count = 0

    for item in parsed:

        name = item["name"]
        phone = item["phone"]

        # Maxsus xizmat nomlari tashqi raqam bilan
        # bazaga tushib ketmasin
        if is_my_service(name):
            continue

        ok = save_record(
            chat_id=update.effective_chat.id
            if update.effective_chat
            else 0,
            category=category,
            name=name,
            phone=phone,
            source_text=parse_text,
        )

        if ok:
            saved_count += 1

    print(
        f"✅ YANGI SAQLANGAN: {saved_count}"
    )

    print(
        "==============================\n"
    )

    # Oddiy ma'lumot yuborilganda bot javob bermaydi.
    # Faqat ma'lumotni bazaga yig'adi.


# =========================================================
# FLASK
# =========================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():

    return "PRO BOT ISHLAYAPTI 🚀"


@flask_app.route("/health")
def health():

    return "OK"


def run_flask():

    port = int(
        os.getenv("PORT", "10000")
    )

    flask_app.run(
        host="0.0.0.0",
        port=port,
    )


# =========================================================
# START BOT
# =========================================================

async def post_init(application):

    print(
        "🔧 Telegram ulanish tayyor..."
    )


def main():

    create_database()

    threading.Thread(
        target=run_flask,
        daemon=True,
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats_command
        )
    )

    application.add_handler(
        CommandHandler(
            "search",
            search_command
        )
    )

    # Text + caption
    application.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.CAPTION
            )
            & ~filters.COMMAND,
            handle_message,
        )
    )

    print(
        "🚀 PRO BOT ISHLADI!"
    )

    print(
        "📥 Avtomatik raqam yig'ish: ON"
    )

    print(
        "🔎 Qidiruv: ON"
    )

    print(
        "🏪 Aptekalar: ON"
    )

    print(
        "🍵 Choyxonalar: ON"
    )

    print(
        "🔧 Maxsus xizmatlar: ON"
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
