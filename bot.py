import os
import re
import sqlite3
import threading
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

# SIZNING XIZMAT RAQAMLARINGIZ
MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

# =========================================================
# MAXSUS XIZMATLAR
# =========================================================

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
# OLDINDAN MA'LUM KATEGORIYALAR
# =========================================================

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

# =========================================================
# QIDIRUVDA E'TIBORSIZ QOLDIRILADIGAN SO'ZLAR
# =========================================================

SEARCH_STOP_WORDS = [
    "nomeri",
    "nomer",
    "raqami",
    "raqam",
    "telefon",
    "telefon raqami",
    "telefon nomeri",
    "telefonini",
    "nomerini",
    "raqamini",
    "bormi",
    "bor",
    "kerak",
    "kerakmi",
    "bering",
    "ber",
    "topib ber",
    "topib bering",
    "topilsin",
    "qayerda",
    "qaysi",
    "kimda",
    "kimning",
    "menga",
    "menga kerak",
    "iltimos",
    "usta",
    "ustasi",
    "xizmati",
    "xizmat",
    "nomer bormi",
    "raqam bormi",
    "telefon bormi",
]

# =========================================================
# TELEFON REGEX
# =========================================================

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
# NORMALIZE
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


# =========================================================
# TELEFONNI TOZALASH
# =========================================================

def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("998"):
        return "+" + digits

    if len(digits) == 9:
        return "+998" + digits

    return phone.strip()


# =========================================================
# TELEFONLARNI TOPISH
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
# MAXSUS XIZMATNI TEKSHIRISH
# =========================================================

def is_my_service(text):
    n = normalize(text)

    for service in MY_SERVICES:
        service_n = normalize(service)

        if service_n in n:
            return True

    return False


# =========================================================
# KATEGORIYA ANIQLASH
# =========================================================

def detect_category(text):
    n = normalize(text)

    # Avval aniq kategoriyalar
    for category, words in CATEGORY_KEYWORDS.items():

        for word in words:

            if normalize(word) in n:
                return category

    # Maxsus xizmat
    for service in MY_SERVICES:

        if normalize(service) in n:
            return service.title()

    return None


# =========================================================
# YANGI KATEGORIYA AVTOMATIK OCHISH
# =========================================================

def auto_category(text, phones):

    category = detect_category(text)

    if category:
        return category

    clean = text

    # Telefonlarni olib tashlash
    for phone in phones:
        clean = clean.replace(phone, " ")

    # Telefon formatlarini olib tashlash
    clean = re.sub(
        r"(?:\+?998[\s\-]?)?\d[\d\s\-]{7,}",
        " ",
        clean
    )

    n = normalize(clean)

    # Qidiruvga xos so'zlarni olib tashlash
    for word in SEARCH_STOP_WORDS:

        n = n.replace(
            normalize(word),
            " "
        )

    n = re.sub(r"\s+", " ", n).strip()

    if not n:
        return "Boshqa"

    words = n.split()

    # Juda uzun gapni kategoriya qilib yubormaslik
    if len(words) > 4:
        words = words[:4]

    category = " ".join(words)

    if not category:
        return "Boshqa"

    return category.title()


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

        # Telefonni olib tashlash
        cleaned = PHONE_RE.sub(" ", line)

        cleaned = re.sub(
            r"\s+",
            " ",
            cleaned
        ).strip()

        if not cleaned:
            continue

        # Belgilarni tozalash
        cleaned = re.sub(
            r"^[^\wА-Яа-яЁёҚқҒғЎўҲҳ]+",
            "",
            cleaned
        )

        if not cleaned:
            continue

        n = normalize(cleaned)

        # Faqat xizmat savolini nom qilib saqlamaslik
        temp = n

        for word in SEARCH_STOP_WORDS:
            temp = temp.replace(
                normalize(word),
                " "
            )

        temp = re.sub(
            r"\s+",
            " ",
            temp
        ).strip()

        if not temp:
            continue

        if len(temp) >= 2:
            candidates.append(cleaned)

    if candidates:
        return candidates[0][:200]

    return category


# =========================================================
# PARSE
# =========================================================

def parse_records(text):

    phones = find_phones(text)

    if not phones:
        return []

    category = detect_category(text)

    if not category:
        category = auto_category(
            text,
            phones
        )

    name = extract_name(
        text,
        phones,
        category
    )

    results = []

    for phone in phones:

        results.append({
            "category": category,
            "name": name,
            "phone": phone,
        })

    return results


# =========================================================
# DATABASEGA SAQLASH
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

    now = datetime.now(
        timezone.utc
    ).isoformat()

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
# QIDIRUV UCHUN SO'ROVNI TOZALASH
# =========================================================

def clean_search_query(query):

    q = normalize(query)

    if not q:
        return ""

    # Avval uzun iboralarni olib tashlaymiz
    stop_words = sorted(
        SEARCH_STOP_WORDS,
        key=len,
        reverse=True
    )

    for word in stop_words:

        q = q.replace(
            normalize(word),
            " "
        )

    q = re.sub(
        r"\s+",
        " ",
        q
    ).strip()

    return q


# =========================================================
# KUCHLI QIDIRUV
# =========================================================

def search_records(query, limit=500):

    q = clean_search_query(query)

    if not q:
        return []

    with db_lock:

        conn = db_connect()

        # -------------------------------------------------
        # 1. TO'LIQ QIDIRUV
        # -------------------------------------------------

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

        # -------------------------------------------------
        # 2. ALOHIDA SO'ZLAR BILAN QIDIRUV
        # -------------------------------------------------

        if not rows:

            words = q.split()

            useful_words = [
                word
                for word in words
                if len(word) >= 2
            ]

            if useful_words:

                conditions = []
                params = []

                for word in useful_words:

                    conditions.append("""
                        (
                            lower(name) LIKE ?
                            OR lower(category) LIKE ?
                            OR lower(source_text) LIKE ?
                        )
                    """)

                    params.extend([
                        f"%{word}%",
                        f"%{word}%",
                        f"%{word}%"
                    ])

                sql = """
                    SELECT *
                    FROM records
                    WHERE
                """

                sql += " AND ".join(
                    conditions
                )

                sql += """
                    ORDER BY id DESC
                    LIMIT ?
                """

                params.append(limit)

                rows = conn.execute(
                    sql,
                    params
                ).fetchall()

        # -------------------------------------------------
        # 3. HAR BIR SO'Z BO'YICHA KENG QIDIRUV
        # -------------------------------------------------

        if not rows:

            words = q.split()

            result_ids = []

            for word in words:

                if len(word) < 2:
                    continue

                temp_rows = conn.execute("""
                    SELECT *
                    FROM records
                    WHERE
                        lower(name) LIKE ?
                        OR lower(category) LIKE ?
                        OR lower(source_text) LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    f"%{word}%",
                    f"%{word}%",
                    f"%{word}%",
                    limit
                )).fetchall()

                for row in temp_rows:

                    if row["id"] not in result_ids:
                        result_ids.append(
                            row["id"]
                        )

            if result_ids:

                placeholders = ",".join(
                    "?" * len(result_ids)
                )

                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM records
                    WHERE id IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (*result_ids, limit)
                ).fetchall()

        conn.close()

    return rows


# =========================================================
# KATEGORIYA QIDIRISH
# =========================================================

def search_category(category, limit=500):

    with db_lock:

        conn = db_connect()

        rows = conn.execute("""
            SELECT *
            FROM records
            WHERE
                lower(category) = lower(?)
                OR lower(category) LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            category,
            f"%{normalize(category)}%",
            limit
        )).fetchall()

        conn.close()

    return rows


# =========================================================
# NATIJALARNI YUBORISH
# =========================================================

async def send_long_result(message, rows):

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

        # Telegram chegarasi
        if len(current) + len(block) > 3800:

            if current:
                await message.reply_text(
                    current.strip()
                )

            current = block

        else:
            current += block

    if current:
        await message.reply_text(
            current.strip()
        )


# =========================================================
# MAXSUS XIZMAT JAVOBI
# =========================================================

async def send_my_service(message):

    await message.reply_text(
        "📞 Kerakli usta raqami:\n\n"
        "+998979600501\n"
        "+998911517577"
    )


# =========================================================
# START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "✅ PRO katalog bot ishlayapti."
    )


# =========================================================
# STATISTIKA
# =========================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

    # Bot xabarlarini qayta ishlamaslik
    if (
        update.effective_user
        and update.effective_user.is_bot
    ):
        return

    text = (
        message.text
        or message.caption
        or ""
    )

    if not text.strip():
        return

    print(
        "📩 MESSAGE:",
        text[:500]
    )

    # =====================================================
    # REPLY XABARINI QO'SHISH
    # =====================================================

    combined_text = text

    if message.reply_to_message:

        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

        if reply_text:
            combined_text += (
                "\n" + reply_text
            )

    # =====================================================
    # MAXSUS XIZMAT
    # =====================================================

    phones_in_text = find_phones(text)

    if (
        is_my_service(text)
        and not phones_in_text
    ):
        await send_my_service(
            message
        )
        return

    # =====================================================
    # TELEFON BORLIGINI TEKSHIRISH
    # =====================================================

    phones = find_phones(
        combined_text
    )

    # =====================================================
    # TELEFON YO'Q
    # DEMAK QIDIRUV
    # =====================================================

    if not phones:

        # -----------------------------------------------
        # 1. KATEGORIYA
        # -----------------------------------------------

        category = detect_category(
            text
        )

        if category:

            rows = search_category(
                category,
                500
            )

            if rows:

                await send_long_result(
                    message,
                    rows
                )

                return

        # -----------------------------------------------
        # 2. KUCHLI MATNLI QIDIRUV
        # -----------------------------------------------

        rows = search_records(
            text,
            500
        )

        if rows:

            await send_long_result(
                message,
                rows
            )

        # TOPILMASA JIM
        return

    # =====================================================
    # MAXSUS XIZMAT + TASHQI RAQAM
    # =====================================================

    if is_my_service(text):
        return

    # =====================================================
    # REKLAMA TEKSHIRISH
    # =====================================================

    # Juda uzun matnni ehtiyotkorlik bilan o'tkazib yuboramiz
    if len(combined_text) > 5000:
        print("🚫 Juda uzun xabar")
        return

    # =====================================================
    # PARSE
    # =====================================================

    parsed = parse_records(
        combined_text
    )

    if not parsed:
        return

    # =====================================================
    # CHAT / USER
    # =====================================================

    chat_id = None
    user_id = None

    if update.effective_chat:
        chat_id = update.effective_chat.id

    if update.effective_user:
        user_id = update.effective_user.id

    # =====================================================
    # SAQLASH
    # =====================================================

    saved_count = 0

    for item in parsed:

        category = item["category"]
        name = item["name"]
        phone = item["phone"]

        # Bizning raqamlarimizni umumiy
        # bazaga yozmaymiz
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
        f"💾 Yangi saqlandi: {saved_count}"
    )


# =========================================================
# FLASK
# =========================================================

app_flask = Flask(__name__)


@app_flask.route("/")
def home():
    return "PRO Telegram Bot OK"


@app_flask.route("/health")
def health():
    return "OK"


def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app_flask.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )


# =========================================================
# TELEGRAM POST INIT
# =========================================================

async def post_init(application):

    print(
        "🔧 Telegram ulanish tayyor..."
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # Bazani yaratish
    init_db()

    # Render health server
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    print(
        "================================"
    )
    print(
        "🚀 PRO DATABASE BOT ISHLADI!"
    )
    print(
        "📥 Avtomatik saqlash: ON"
    )
    print(
        "📂 Avtomatik kategoriya: ON"
    )
    print(
        "🔎 Kuchli qidiruv: ON"
    )
    print(
        "🔁 Dublikat himoyasi: ON"
    )
    print(
        "💬 Reply o'qish: ON"
    )
    print(
        "🤫 Topilmasa jim: ON"
    )
    print(
        "📱 Savol shaklini tushunish: ON"
    )
    print(
        "================================"
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

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
        MessageHandler(
            filters.TEXT
            | filters.CaptionRegex(".+"),
            handle_message
        )
    )

    # FAQAT BITTA POLLING
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
