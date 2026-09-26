import os
import re
import sqlite3
import threading
import asyncio
from datetime import datetime, timezone

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
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

DB_FILE = "bot_database.db"

MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

# Sizning xizmatlaringiz
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

# Oldindan tanilgan kategoriyalar
CATEGORY_KEYWORDS = {
    "Aptekalar": [
        "apteka",
        "aptekalar",
        "aptekasi",
        "dorixona",
        "dori",
        "dori-darmon",
        "аптека",
        "аптек",
        "дорихона",
    ],

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

    "Konditsioner": [
        "konditsioner",
        "konditsaner",
        "kanditsioner",
        "кондиционер",
    ],

    "Katyol": [
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
    ],
}

# Reklama sifatida ko‘riladigan so‘zlar
AD_WORDS = [
    "reklama",
    "aksiya",
    "chegirma",
    "sotiladi",
    "sotamiz",
    "narxi",
    "zakaz",
    "buyurtma",
]

# Telefon raqami
PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+?998[\s\-]?)?"
    r"(?:\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})"
    r"(?!\d)"
)

db_lock = threading.Lock()

# =========================================================
# DATABASE
# =========================================================

def db_connect():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
        timeout=30
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = db_connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                source_text TEXT,
                chat_id INTEGER,
                user_id INTEGER,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_unique_record
            ON records(category, name, phone)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_category
            ON records(category)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_phone
            ON records(phone)
        """)

        conn.commit()
        conn.close()


# =========================================================
# MATN NORMALIZATSIYA
# =========================================================

def normalize(text):
    if not text:
        return ""

    text = text.lower().strip()

    replacements = {
        "қ": "q",
        "ғ": "g",
        "ў": "o",
        "ҳ": "h",
        "ё": "yo",
        "ү": "u",
        "ө": "o",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("998"):
        return "+" + digits

    if len(digits) == 9:
        return "+998" + digits

    return phone.strip()


# =========================================================
# TELEFON TOPISH
# =========================================================

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
# MAXSUS XIZMATNI ANIQLASH
# =========================================================

def is_my_service(text):
    n = normalize(text)

    for service in MY_SERVICES:
        if normalize(service) in n:
            return True

    return False


# =========================================================
# KATEGORIYA ANIQLASH
# =========================================================

def detect_category(text):
    n = normalize(text)

    # Avval mavjud kategoriyalar
    for category, words in CATEGORY_KEYWORDS.items():
        for word in words:
            if normalize(word) in n:
                return category

    # Maxsus xizmatlar
    for service in MY_SERVICES:
        if normalize(service) in n:
            return service.title()

    return None


# =========================================================
# YANGI KATEGORIYA AVTOMATIK ANIQLASH
# =========================================================

def auto_category(text, phones):
    """
    Bazada kategoriya bo‘lmasa,
    matndan yangi kategoriya yaratadi.
    """

    existing = detect_category(text)

    if existing:
        return existing

    clean = text

    # telefonlarni olib tashlash
    for phone in phones:
        clean = clean.replace(phone, " ")

    clean = re.sub(
        r"(?:\+?998[\s\-]?)?\d[\d\s\-]{7,}",
        " ",
        clean
    )

    # keraksiz so‘zlar
    remove_words = [
        "nomeri",
        "nomer",
        "raqami",
        "raqam",
        "telefon",
        "tel",
        "telefon raqam",
        "usta",
        "bor",
        "bormi",
        "kerak",
        "kerakli",
        "xizmat",
        "xizmati",
        "qiladi",
        "qilamiz",
        "uyga",
        "borib",
        "xizmat",
        "reklama",
    ]

    n = normalize(clean)

    for word in remove_words:
        n = n.replace(normalize(word), " ")

    n = re.sub(r"\s+", " ", n).strip()

    if not n:
        return "Boshqa"

    # juda uzun matnni kategoriya qilib yubormaslik
    words = n.split()

    if len(words) > 4:
        words = words[:4]

    category = " ".join(words)

    return category.title() if category else "Boshqa"


# =========================================================
# REKLAMA TEKSHIRISH
# =========================================================

def is_advertisement(text):
    n = normalize(text)

    phones = find_phones(text)

    if not phones:
        return False

    # Oddiy xizmat e'loni sifatida qabul qilamiz
    service_words = [
        "usta",
        "xizmat",
        "ta'mir",
        "tamir",
        "tozalash",
        "o'rnatish",
        "ornatish",
        "yechish",
        "sotaman",
        "sotiladi",
        "qilamiz",
        "qiladi",
    ]

    # Faqat "reklama" degan so'z borligi
    # saqlashga to‘sqinlik qilmasin
    # chunki guruh katalogi uchun reklama ham ma'lumot bo‘lishi mumkin.

    for word in service_words:
        if word in n:
            return False

    # juda uzun reklama matni
    if len(text) > 2500:
        return True

    return False


# =========================================================
# NOMNI ANIQLASH
# =========================================================

def extract_name(text, phones, category):
    lines = text.splitlines()

    candidates = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # telefon bo‘lgan qatorni tozalash
        cleaned = PHONE_RE.sub(" ", line)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            continue

        # emoji va belgilar
        cleaned = re.sub(
            r"^[^\wА-Яа-яЁёҚқҒғЎўҲҳ]+",
            "",
            cleaned
        )

        if not cleaned:
            continue

        candidates.append(cleaned)

    # Eng yaxshi nom
    if candidates:
        for candidate in candidates:
            n = normalize(candidate)

            if n in ["apteka", "aptekalar", "choyxona", "choyxonalar"]:
                continue

            if len(n) >= 2:
                return candidate[:200]

    return category


# =========================================================
# RECORD PARSE
# =========================================================

def parse_records(text):
    phones = find_phones(text)

    if not phones:
        return []

    category = detect_category(text)

    if not category:
        category = auto_category(text, phones)

    name = extract_name(text, phones, category)

    results = []

    for phone in phones:
        results.append({
            "category": category,
            "name": name,
            "phone": phone,
        })

    return results


# =========================================================
# SAQLASH
# =========================================================

def save_record(
    category,
    name,
    phone,
    source_text="",
    chat_id=None,
    user_id=None
):
    phone = normalize_phone(phone)

    if not category:
        category = "Boshqa"

    if not name:
        name = category

    now = datetime.now(timezone.utc).isoformat()

    with db_lock:
        conn = db_connect()

        cur = conn.execute("""
            INSERT OR IGNORE INTO records
            (
                category,
                name,
                phone,
                source_text,
                chat_id,
                user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            category,
            name,
            phone,
            source_text[:5000],
            chat_id,
            user_id,
            now
        ))

        inserted = cur.rowcount > 0

        conn.commit()
        conn.close()

    return inserted


# =========================================================
# QIDIRUV
# =========================================================

def search_records(query, limit=500):
    q = normalize(query)

    if not q:
        return []

    with db_lock:
        conn = db_connect()

        rows = conn.execute("""
            SELECT *
            FROM records
            WHERE
                lower(name) LIKE ?
                OR lower(category) LIKE ?
                OR lower(phone) LIKE ?
                OR lower(source_text) LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            f"%{q}%",
            f"%{q}%",
            f"%{q}%",
            f"%{q}%",
            limit
        )).fetchall()

        conn.close()

    return rows


def search_category(category, limit=500):
    with db_lock:
        conn = db_connect()

        rows = conn.execute("""
            SELECT *
            FROM records
            WHERE lower(category) = lower(?)
            ORDER BY id DESC
            LIMIT ?
        """, (
            category,
            limit
        )).fetchall()

        conn.close()

    return rows


# =========================================================
# NATIJANI CHIQARISH
# =========================================================

def format_results(rows):
    if not rows:
        return ""

    lines = []

    seen = set()

    for row in rows:
        key = (
            row["category"],
            row["name"],
            row["phone"]
        )

        if key in seen:
            continue

        seen.add(key)

        lines.append(
            f"📂 {row['category']}\n"
            f"🏪 {row['name']}\n"
            f"📞 {row['phone']}"
        )

    return "\n\n".join(lines)


async def send_long_result(message, rows):
    """
    Telegram xabar chegarasiga sig‘maydigan
    natijalarni bir nechta xabarga bo‘lib yuboradi.
    """

    if not rows:
        return

    current = ""

    seen = set()

    for row in rows:
        key = (
            row["category"],
            row["name"],
            row["phone"]
        )

        if key in seen:
            continue

        seen.add(key)

        block = (
            f"📂 {row['category']}\n"
            f"🏪 {row['name']}\n"
            f"📞 {row['phone']}\n\n"
        )

        if len(current) + len(block) > 3800:
            if current:
                await message.reply_text(current.strip())

            current = block
        else:
            current += block

    if current:
        await message.reply_text(current.strip())


# =========================================================
# MAXSUS XIZMAT JAVOBI
# =========================================================

async def send_my_service(message):
    text = (
        "📞 Kerakli usta raqami:\n\n"
        "+998979600501\n"
        "+998911517577"
    )

    await message.reply_text(text)


# =========================================================
# START
# =========================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ PRO katalog bot ishlayapti."
    )


# =========================================================
# STATISTIKA
# =========================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db_lock:
        conn = db_connect()

        total = conn.execute(
            "SELECT COUNT(*) FROM records"
        ).fetchone()[0]

        categories = conn.execute(
            "SELECT COUNT(DISTINCT category) FROM records"
        ).fetchone()[0]

        conn.close()

    await update.message.reply_text(
        f"📊 BAZA\n\n"
        f"📞 Jami raqamlar: {total}\n"
        f"📂 Kategoriyalar: {categories}"
    )


# =========================================================
# ASOSIY HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_message:
        return

    message = update.effective_message

    # Botning o‘z xabarini qayta ishlamaslik
    if update.effective_user and update.effective_user.is_bot:
        return

    text = message.text or message.caption or ""

    if not text.strip():
        return

    print("📩 MESSAGE:", text[:500])

    # -----------------------------------------------------
    # 1. MAXSUS XIZMAT QIDIRUVI
    # -----------------------------------------------------

    if is_my_service(text) and not find_phones(text):
        await send_my_service(message)
        return

    # -----------------------------------------------------
    # 2. REPLY XABARINI HAM O‘QISH
    # -----------------------------------------------------

    combined_text = text

    if message.reply_to_message:
        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

        if reply_text:
            combined_text += "\n" + reply_text

    # -----------------------------------------------------
    # 3. TELEFON BOR-YO‘QLIGI
    # -----------------------------------------------------

    phones = find_phones(combined_text)

    # -----------------------------------------------------
    # 4. TELEFON YO‘Q BO‘LSA — QIDIRUV
    # -----------------------------------------------------

    if not phones:

        category = detect_category(text)

        # Kategoriya bo‘yicha qidirish
        if category:
            rows = search_category(category, 500)

            if rows:
                await send_long_result(message, rows)
                return

        # Oddiy qidiruv
        rows = search_records(text, 500)

        if rows:
            await send_long_result(message, rows)

        # TOPILMASA HECH NIMA YO‘Q
        return

    # -----------------------------------------------------
    # 5. MAXSUS XIZMAT + TASHQI RAQAM
    # -----------------------------------------------------

    # Agar matn bizning xizmatimiz bo‘lsa,
    # tashqi raqamni bazaga kiritmaymiz.
    if is_my_service(text):
        return

    # -----------------------------------------------------
    # 6. REKLAMA / KERAKSIZ MATN
    # -----------------------------------------------------

    if is_advertisement(combined_text):
        print("🚫 Reklama sifatida o'tkazib yuborildi")
        return

    # -----------------------------------------------------
    # 7. PARSE
    # -----------------------------------------------------

    parsed = parse_records(combined_text)

    if not parsed:
        return

    # -----------------------------------------------------
    # 8. CHAT / USER
    # -----------------------------------------------------

    chat_id = None
    user_id = None

    if update.effective_chat:
        chat_id = update.effective_chat.id

    if update.effective_user:
        user_id = update.effective_user.id

    # -----------------------------------------------------
    # 9. BAZAGA SAQLASH
    # -----------------------------------------------------

    saved_count = 0

    for item in parsed:

        category = item["category"]
        name = item["name"]
        phone = item["phone"]

        # Bizning shaxsiy raqamlarni
        # katalog yozuvi sifatida saqlamaslik
        if phone in MY_PHONES:
            continue

        inserted = save_record(
            category=category,
            name=name,
            phone=phone,
            source_text=combined_text,
            chat_id=chat_id,
            user_id=user_id
        )

        if inserted:
            saved_count += 1

    print(
        f"💾 Saqlandi: {saved_count} | "
        f"topildi: {len(parsed)}"
    )

    # Ma'lumot yuborgan odamga bot javob bermaydi.
    return


# =========================================================
# FLASK SERVER
# =========================================================

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "PRO Telegram Bot OK"


@app_flask.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 10000))

    app_flask.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )


# =========================================================
# TELEGRAM BOT
# =========================================================

async def post_init(application):
    print("🔧 Telegram ulanish tayyor...")


def main():

    init_db()

    # Flask server alohida thread
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    print("🚀 PRO AUTO DATABASE BOT ISHLADI!")
    print("📥 Avtomatik saqlash: ON")
    print("📂 Avtomatik kategoriya: ON")
    print("🔎 Qidiruv: ON")
    print("🔁 Dublikat himoyasi: ON")
    print("💬 Reply o‘qish: ON")
    print("🤫 Topilmasa jim: ON")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        CommandHandler("stats", stats_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.CaptionRegex(".+"),
            handle_message
        )
    )

    # Bitta polling instance
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
