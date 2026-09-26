import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

DB_FILE = "bot_database.db"

# FAQAT SIZNING MAXSUS XIZMAT RAQAMLARINGIZ
MY_PHONES = [
    "+998979600501",
    "+998911517577",
]

# =========================================================
# MAXSUS XIZMATLAR
# Bu kategoriyalarda boshqa odamlarning raqami SAQLANMAYDI
# =========================================================

MY_SERVICES = [
    # Konditsioner
    "konditsioner",
    "konditsaner",
    "kanditsioner",
    "kansaner",
    "konditsioner usta",
    "кондиционер",

    # Katyol / qozon
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

    # Santexnika
    "santexnik",
    "santexnika",
    "сантехник",
    "сантехника",

    # Televizor
    "televizor",
    "televizor usta",
    "телевизор",

    # Perforator
    "perforator",
    "perforatorchi",
    "perfaratorchi",
    "перфоратор",
    "перфораторчи",

    # Kir mashina
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
    "stiralka",
    "stiralka usta",
    "стиралка",
    "стиралка уста",
    "стиральная машина",
    "кир ювиш машинаси",
    "кир машина",
    "автомат стиралка",
]

# =========================================================
# KATEGORIYALAR
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
        "kansaner",
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

    "Santexnika": [
        "santexnik",
        "santexnika",
        "сантехник",
        "сантехника",
    ],

    "Televizor": [
        "televizor",
        "televizor usta",
        "телевизор",
    ],

    "Perforator": [
        "perforator",
        "perforatorchi",
        "perfaratorchi",
        "перфоратор",
        "перфораторчи",
    ],

    "Kir mashina": [
        "kir mashina",
        "kir mashinasi",
        "kir yuvish mashinasi",
        "kirmashina",
        "kirmoshina",
        "stiralka",
        "стиралка",
        "стиральная машина",
        "кир ювиш машинаси",
        "кир машина",
    ],
}

# =========================================================
# QIDIRUVDA OLIB TASHLANADIGAN SO'ZLAR
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

# =========================================================
# DATABASE
# =========================================================

db_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

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
        CREATE UNIQUE INDEX IF NOT EXISTS unique_record
        ON records(category, name, phone)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_category
        ON records(category)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_phone
        ON records(phone)
    """)

    conn.commit()

    return conn


get_db().close()


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

    found = []

    for match in PHONE_RE.findall(text):
        phone = normalize_phone(match)

        if phone not in found:
            found.append(phone)

    return found


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

    # Avval maxsus kategoriyalar
    for category, keywords in CATEGORY_KEYWORDS.items():

        for keyword in keywords:
            if normalize(keyword) in text_n:
                return category

    return None


def clean_search_query(query):
    text = normalize(query)

    for word in sorted(
        SEARCH_STOP_WORDS,
        key=len,
        reverse=True
    ):
        text = text.replace(normalize(word), " ")

    text = re.sub(r"[^\w\s'-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def auto_category(text):
    """
    Agar kategoriya oldindan mavjud bo'lmasa,
    xabardan avtomatik kategoriya yaratadi.
    """

    category = detect_category(text)

    if category:
        return category

    text_n = normalize(text)

    for word in SEARCH_STOP_WORDS:
        text_n = text_n.replace(normalize(word), " ")

    phones = find_phones(text)

    for phone in phones:
        text_n = text_n.replace(phone, " ")

    text_n = re.sub(r"[^\w\s'-]", " ", text_n)
    text_n = re.sub(r"\s+", " ", text_n).strip()

    if not text_n:
        return "Boshqa"

    words = text_n.split()

    # Juda uzun kategoriya bo'lib ketmasligi uchun
    words = words[:4]

    category = " ".join(words)

    return category.title() if category else "Boshqa"


def extract_name(text, phone):
    """
    Telefon raqamidan oldingi / atrofidagi
    matndan nomni aniqlash.
    """

    clean = text.replace(phone, " ")

    clean = re.sub(
        r"\+?998[\d\s\-]{9,15}",
        " ",
        clean
    )

    clean = re.sub(r"\s+", " ", clean).strip()

    # Emoji va belgilarni kamaytirish
    clean = clean.strip(" -:|•📞☎️")

    if not clean:
        return "Nomsiz"

    # Juda uzun xabarni nom sifatida saqlamaslik
    if len(clean) > 150:
        clean = clean[:150]

    return clean


def parse_records(text):
    phones = find_phones(text)

    if not phones:
        return []

    category = auto_category(text)

    records = []

    for phone in phones:

        name = extract_name(text, phone)

        records.append({
            "category": category,
            "name": name,
            "phone": phone,
        })

    return records


def save_record(
    category,
    name,
    phone,
    source_text,
    chat_id,
    user_id
):
    phone = normalize_phone(phone)

    if is_my_phone(phone):
        return False

    now = datetime.now(
        timezone.utc
    ).isoformat()

    with db_lock:

        conn = get_db()

        cursor = conn.execute("""
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
            source_text,
            chat_id,
            user_id,
            now,
        ))

        conn.commit()

        inserted = cursor.rowcount == 1

        conn.close()

    return inserted


# =========================================================
# ADMIN TEKSHIRISH
# =========================================================

async def is_group_admin(update, context):
    """
    Faqat GROUP / SUPERGROUP adminlarini aniqlaydi.
    """

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    if chat.type not in (
        "group",
        "supergroup",
    ):
        return False

    try:

        member = await context.bot.get_chat_member(
            chat.id,
            user.id
        )

        return member.status in (
            "administrator",
            "creator",
        )

    except Exception as e:

        print(
            "Admin tekshirish xatosi:",
            e
        )

        return False


# =========================================================
# QIDIRUV
# =========================================================

def search_category(category):
    with db_lock:

        conn = get_db()

        rows = conn.execute("""
            SELECT category, name, phone
            FROM records
            WHERE lower(category) = lower(?)
            ORDER BY name
        """, (category,)).fetchall()

        conn.close()

    return rows


def search_records(query):
    cleaned = clean_search_query(query)

    if not cleaned:
        return []

    words = cleaned.split()

    with db_lock:

        conn = get_db()

        # Avval butun ibora bo'yicha
        like_query = f"%{cleaned}%"

        rows = conn.execute("""
            SELECT category, name, phone
            FROM records
            WHERE
                lower(category) LIKE lower(?)
                OR lower(name) LIKE lower(?)
                OR lower(source_text) LIKE lower(?)
            ORDER BY category, name
            LIMIT 500
        """, (
            like_query,
            like_query,
            like_query,
        )).fetchall()

        # Agar topilmasa, alohida so'zlar
        if not rows:

            found_ids = set()
            result = []

            for word in words:

                if len(word) < 2:
                    continue

                like_word = f"%{word}%"

                temp = conn.execute("""
                    SELECT id, category, name, phone
                    FROM records
                    WHERE
                        lower(category) LIKE lower(?)
                        OR lower(name) LIKE lower(?)
                        OR lower(source_text) LIKE lower(?)
                    ORDER BY category, name
                    LIMIT 500
                """, (
                    like_word,
                    like_word,
                    like_word,
                )).fetchall()

                for row in temp:

                    if row[0] not in found_ids:

                        found_ids.add(row[0])

                        result.append(
                            (
                                row[1],
                                row[2],
                                row[3]
                            )
                        )

            rows = result

        conn.close()

    return rows


# =========================================================
# NATIJA YUBORISH
# =========================================================

async def send_long_result(
    update,
    lines
):

    if not lines:
        return

    text = "\n".join(lines)

    # Telegram limitiga yaqinlashtirmaymiz
    chunk_size = 3500

    while text:

        if len(text) <= chunk_size:

            await update.message.reply_text(
                text
            )

            break

        cut = text.rfind(
            "\n",
            0,
            chunk_size
        )

        if cut == -1:
            cut = chunk_size

        part = text[:cut]

        await update.message.reply_text(
            part
        )

        text = text[cut:].lstrip()


async def send_my_services(update):

    await update.message.reply_text(
        "+998979600501\n"
        "+998911517577"
    )


# =========================================================
# ASOSIY XABAR HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message

    if not message:
        return

    # Botlarning xabarlarini qayta ishlamaymiz
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""

    if not text:
        return

    # Reply qilingan xabar matnini ham qo'shamiz
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

    # -----------------------------------------------------
    # ADMINMI?
    # -----------------------------------------------------

    admin = await is_group_admin(
        update,
        context
    )

    phones = find_phones(text)

    special = is_special_service(text)

    # -----------------------------------------------------
    # 1. MAXSUS XIZMAT QIDIRUVI
    # -----------------------------------------------------

    if special and not phones:

        await send_my_services(update)

        return

    # -----------------------------------------------------
    # 2. RAQAM YO'Q BO'LSA — QIDIRUV
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

        # Hech narsa topilmasa
        # BOT JIM TURADI
        if not rows:
            return

        lines = []

        for category, name, phone in rows:

            lines.append(
                f"📂 {category}\n"
                f"🏷 {name}\n"
                f"📞 {phone}"
            )

        await send_long_result(
            update,
            lines
        )

        return

    # -----------------------------------------------------
    # 3. MAXSUS XIZMAT + BOSHQA RAQAM
    # -----------------------------------------------------

    if special:

        # Boshqa odamlarning raqamini
        # MAXSUS XIZMAT sifatida saqlamaymiz.

        # Faqat sizning raqamingiz chiqadi.
        await send_my_services(update)

        return

    # -----------------------------------------------------
    # 4. RAQAMLI XABAR
    # -----------------------------------------------------

    # FAQAT ADMIN RAQAMI SAQLANADI
    if not admin:

        # Oddiy foydalanuvchining raqami
        # UMUMAN saqlanmaydi.
        return

    # -----------------------------------------------------
    # 5. ADMIN RAQAMLARINI SAQLASH
    # -----------------------------------------------------

    records = parse_records(text)

    saved_count = 0

    for record in records:

        phone = record["phone"]

        # Maxsus xizmat raqamlarini yana
        # bazaga yozmaymiz.
        if is_my_phone(phone):
            continue

        saved = save_record(
            category=record["category"],
            name=record["name"],
            phone=phone,
            source_text=text,
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
        )

        if saved:
            saved_count += 1

    # ADMIN XABARIGA JAVOB BERMAYMIZ
    # faqat bazaga saqlaymiz.


# =========================================================
# FLASK — RENDER UCHUN
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
        "PRO BOT ISHLADI..."
    )

    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
