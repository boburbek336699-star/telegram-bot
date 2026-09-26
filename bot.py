import os
import re
import sqlite3
import threading
from datetime import datetime

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# BOT TOKEN
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

# =========================================================
# DATABASE
# =========================================================

DB_FILE = "bot_database.db"
DB_LOCK = threading.Lock()

# =========================================================
# SIZNING MAXSUS XIZMATLARINGIZ
# =========================================================

MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

MY_SERVICES = [
    "konditsioner",
    "konditsaner",
    "kanditsioner",
    "kansaner",
    "кондиционер",

    "katyol",
    "katel",
    "kotel",
    "qozon",
    "gaz qozon",
    "vaillant",
    "vailant",
    "valiant",
    "vaylant",
    "вайлант",
    "котел",
    "котёл",
    "қозон",

    "santexnik",
    "santexnika",
    "сантехник",
    "сантехника",

    "televizor",
    "televizor usta",
    "телевизор",
    "телевизор уста",

    "perforatorchi",
    "perfaratorchi",
    "perforator",
    "перфораторчи",
    "перфоратор",

    "kir mashina",
    "kir mashinasi",
    "kir yuvish mashinasi",
    "kir yuvish mashina",
    "kirmashina",
    "kirmoshina",
    "kirmashina usta",
    "kirmoshina usta",

    "avtomat kir mashina",
    "avtomat kir yuvish mashinasi",
    "avtomat kir mashina usta",

    "stiralka",
    "stiralka usta",
    "стиралка",
    "стиралка уста",
    "стиральная машина",
    "стиральная машина уста",

    "кир ювиш машинаси",
    "кир машина",
    "автомат стиралка",
]

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
# REKLAMA SO'ZLARI
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
# PHONE REGEX
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

# =========================================================
# DATABASE YARATISH
# =========================================================

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

    print("🗄 DATABASE TAYYOR")


# =========================================================
# MATNNI TOZALASH
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
# TELEFON
# =========================================================

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

    for match in PHONE_RE.findall(text):

        phone = normalize_phone(match)

        if phone not in result:
            result.append(phone)

    return result


# =========================================================
# MAXSUS XIZMATNI ANIQLASH
# =========================================================

def is_my_service(text):

    n = normalize(text)

    for service in MY_SERVICES:

        if normalize(service) in n:
            return True

    return False


# =========================================================
# KATEGORIYANI ANIQLASH
# =========================================================

def detect_category(text):

    n = normalize(text)

    for category, keywords in CATEGORY_KEYWORDS.items():

        for keyword in keywords:

            if normalize(keyword) in n:
                return category

    return "Boshqa"


# =========================================================
# REKLAMA ANIQLASH
# =========================================================

def is_advertisement(text):

    n = normalize(text)

    score = 0

    for word in AD_WORDS:

        if normalize(word) in n:
            score += 2

    service_count = 0

    for word in SERVICE_WORDS:

        if normalize(word) in n:
            service_count += 1

    if service_count >= 3:
        score += 3

    if "universal master" in n:
        return True

    return score >= 4


# =========================================================
# QATORNI TOZALASH
# =========================================================

def clean_line(line):

    line = line.strip()

    line = re.sub(
        r"^[\s\-–—•▪️🔹🔸📞☎️📱👉🏻👉🏼👉🏽👉🏾👉🏿]+",
        "",
        line
    )

    return line.strip(" -–—:|")


def is_meaningful(line):

    if not line:
        return False

    n = normalize(line)

    if len(n) < 2:
        return False

    bad = [
        "aptekalar",
        "choyxonalar",
        "kerakli raqam",
        "kerakli nomer",
    ]

    if n in bad:
        return False

    return True


# =========================================================
# NOM + TELEFONLARNI AJRATISH
# =========================================================

def parse_records(text):

    if not text:
        return []

    lines = text.splitlines()

    records = []

    current_name = ""

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        phones = find_phones(line)

        # -------------------------------------------------
        # TELEFON BOR
        # -------------------------------------------------

        if phones:

            # Telefonni olib tashlaymiz
            label = PHONE_RE.sub("", line)

            label = clean_line(label)

            if label:

                if current_name:

                    if normalize(label) not in normalize(current_name):

                        name = (
                            f"{current_name} — {label}"
                        )

                    else:

                        name = current_name

                else:

                    name = label

            else:

                name = current_name

            if not name:
                name = "Nomi ko'rsatilmagan"

            for phone in phones:

                records.append({
                    "name": name,
                    "phone": phone,
                })

        # -------------------------------------------------
        # TELEFON YO'Q
        # -------------------------------------------------

        else:

            cleaned = clean_line(line)

            if is_meaningful(cleaned):

                current_name = cleaned

    return records


# =========================================================
# BAZAGA SAQLASH
# =========================================================

def save_record(
    chat_id,
    category,
    name,
    phone,
    source_text
):

    with DB_LOCK:

        conn = get_db()

        existing = conn.execute(
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
            )
        ).fetchone()

        if existing:

            conn.close()

            print(
                f"♻️ OLDIN BOR: "
                f"{category} | {name} | {phone}"
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
            )
        )

        conn.commit()
        conn.close()

    print(
        f"💾 SAQLANDI: "
        f"{category} | {name} | {phone}"
    )

    return True


# =========================================================
# QIDIRUV
# =========================================================

def search_records(query, limit=50):

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
            ORDER BY name, phone
            LIMIT ?
            """,
            (
                f"%{q}%",
                f"%{q}%",
                f"%{q}%",
                limit,
            )
        ).fetchall()

        conn.close()

    return rows


def search_category(category, limit=100):

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
            )
        ).fetchall()

        conn.close()

    return rows


# =========================================================
# NATIJANI CHIROYLI CHIQARISH
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

        if row["phone"] not in grouped[key]:

            grouped[key].append(
                row["phone"]
            )

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

    result = "\n".join(output)

    return result[:3900]


# =========================================================
# MAXSUS XIZMAT JAVOBI
# =========================================================

async def send_my_service(update):

    await update.effective_message.reply_text(
        "📞 KERAKLI RAQAM\n\n"
        f"1️⃣ {MY_PHONES[0]}\n"
        f"2️⃣ {MY_PHONES[1]}"
    )


# =========================================================
# START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.effective_message.reply_text(
        "🤖 PRO KERAKLI RAQAMLAR BOT\n\n"
        "Kerakli nom yoki xizmatni yozing.\n\n"
        "Masalan:\n"
        "🔎 apteka\n"
        "🔎 choyxona\n"
        "🔎 Romanka\n"
        "🔎 Malina choy\n\n"
        "📥 Yangi raqamlar avtomatik yig'iladi."
    )


# =========================================================
# STATISTIKA
# =========================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    result = [
        "📊 PRO BOT BAZASI",
        "",
        f"📞 Jami yozuvlar: {total}",
        "",
    ]

    for row in categories:

        result.append(
            f"• {row[0]}: {row[1]}"
        )

    await update.effective_message.reply_text(
        "\n".join(result)
    )


# =========================================================
# SEARCH COMMAND
# =========================================================

async def search_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = " ".join(
        context.args
    ).strip()

    if not query:

        await update.effective_message.reply_text(
            "🔎 Masalan:\n\n"
            "/search apteka\n"
            "/search Romanka\n"
            "/search Malina choy"
        )

        return

    rows = search_records(query)

    await update.effective_message.reply_text(
        format_results(rows)
    )


# =========================================================
# ASOSIY XABAR
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # Bot yuborgan xabarni qayta o'qimaydi
    if message.from_user:

        if message.from_user.is_bot:
            return

    text = (
        message.text
        or message.caption
        or ""
    )

    if not text:
        return

    print("")
    print("================================")
    print("📥 YANGI XABAR:")
    print(text[:2000])

    # =====================================================
    # MAXSUS XIZMAT
    # =====================================================

    if is_my_service(text):

        print(
            "⭐ MAXSUS XIZMAT ANIQLANDI"
        )

        await send_my_service(update)

        # Boshqalarning raqamini saqlamaymiz
        return

    # =====================================================
    # REPLY QILINGAN XABAR
    # =====================================================

    parse_text = text

    current_phones = find_phones(text)

    if (
        not current_phones
        and message.reply_to_message
    ):

        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

        if reply_text:

            parse_text = reply_text

            print(
                "↩️ REPLY XABAR HAM TEKSHIRILDI"
            )

    # =====================================================
    # TELEFONLAR
    # =====================================================

    phones = find_phones(parse_text)

    print(
        f"📞 TOPILGAN: {phones}"
    )

    # =====================================================
    # RAQAM YO'Q = QIDIRUV
    # =====================================================

    if not phones:

        category = detect_category(text)

        # Kategoriya qidiruvi
        if category != "Boshqa":

            rows = search_category(
                category,
                100
            )

            if rows:

                await update.effective_message.reply_text(
                    format_results(rows)
                )

                return

        # Nom qidiruvi
        rows = search_records(
            text,
            50
        )

        if rows:

            await update.effective_message.reply_text(
                format_results(rows)
            )
            
        return

    # =====================================================
    # REKLAMA
    # =====================================================

    if is_advertisement(parse_text):

        print(
            "🚫 REKLAMA ANIQLANDI — SAQLANMADI"
        )

        return

    # =====================================================
    # KATEGORIYA
    # =====================================================

    category = detect_category(
        parse_text
    )

    print(
        f"🏷 KATEGORIYA: {category}"
    )

    # =====================================================
    # PARSER
    # =====================================================

    parsed = parse_records(
        parse_text
    )

    # Parser hech narsa chiqarmasa
    if not parsed:

        for phone in phones:

            parsed.append({
                "name": "Nomi ko'rsatilmagan",
                "phone": phone,
            })

    # =====================================================
    # SAQLASH
    # =====================================================

    saved = 0

    chat_id = 0

    if update.effective_chat:

        chat_id = update.effective_chat.id

    for item in parsed:

        name = item["name"]
        phone = item["phone"]

        # Maxsus xizmat nomi bilan
        # tashqi raqam saqlanmasin
        if is_my_service(name):

            continue

        if save_record(
            chat_id=chat_id,
            category=category,
            name=name,
            phone=phone,
            source_text=parse_text,
        ):

            saved += 1

    print(
        f"✅ YANGI SAQLANDI: {saved}"
    )

    print(
        "================================"
    )


# =========================================================
# FLASK SERVER
# =========================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():

    return "PRO KERAKLI RAQAMLAR BOT ISHLAYAPTI 🚀"


@flask_app.route("/health")
def health():

    return "OK"


def run_flask():

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    flask_app.run(
        host="0.0.0.0",
        port=port,
    )


# =========================================================
# TELEGRAM INIT
# =========================================================

async def post_init(application):

    print(
        "🔧 Telegram ulanish tayyor..."
    )


# =========================================================
# MAIN
# =========================================================

def main():

    create_database()

    # Flask server
    threading.Thread(
        target=run_flask,
        daemon=True,
    ).start()

    # Telegram
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

    # Text va caption
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

    print("")
    print("================================")
    print("🚀 PRO BOT ISHLADI!")
    print("📥 Avtomatik raqam yig'ish: ON")
    print("🔎 Qidiruv: ON")
    print("🏪 Aptekalar: ON")
    print("🍵 Choyxonalar: ON")
    print("🔧 Maxsus xizmatlar: ON")
    print("📞 Ko'p raqamli yozuvlar: ON")
    print("🏷 Filial/manzil: ON")
    print("================================")
    print("")

    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
