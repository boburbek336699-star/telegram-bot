import os
import re
import sqlite3
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters


# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Render Environment Variables ni tekshiring.")


MY_PHONES = [
    "+998979600501",
    "+998911517577",
]


# Faqat shu xizmatlarda boshqa odamlarning raqami saqlanmaydi
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


CATEGORY_KEYWORDS = {
    "Choyxonalar": [
        "choyxona",
        "choyxonasi",
        "choyxonalar",
        "oshxona",
        "restoran",
        "kafe",
        "kabob",
    ],

    "Aptekalar": [
        "apteka",
        "aptekalar",
        "dorixona",
        "dori-darmon",
    ],
}


# Reklama ekanini aniqlashga yordam beradigan so'zlar
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
    "murojaat",
]


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "PRO BOT ISHLAYAPTI"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================================================
# DATABASE
# =========================================================

DB_FILE = "bot_database.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            category TEXT,
            name TEXT,
            phone TEXT,
            source_text TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# MATN FUNKSIYALARI
# =========================================================

def normalize(text):
    if not text:
        return ""

    text = text.lower()

    replacements = {
        "ў": "ў",
        "қ": "қ",
        "ғ": "ғ",
        "ҳ": "ҳ",
        "ё": "ё",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def find_phones(text):
    if not text:
        return []

    pattern = r"(?:\+998|998)\s*\d{2}\s*\d{3}\s*\d{2}\s*\d{2}"

    found = re.findall(pattern, text)

    result = []

    for phone in found:
        digits = re.sub(r"\D", "", phone)

        if digits.startswith("998") and len(digits) == 12:
            formatted = "+" + digits

            if formatted not in result:
                result.append(formatted)

    return result


def is_my_service(text):
    normalized = normalize(text)

    for service in MY_SERVICES:
        if normalize(service) in normalized:
            return True

    return False


def detect_category(text):
    normalized = normalize(text)

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if normalize(keyword) in normalized:
                return category

    return None


def is_category_query(text):
    normalized = normalize(text)

    if normalized in [
        "choyxona",
        "choyxonalar",
        "choyxonasi",
        "choyxonalarni",
        "choyxona kerak",
        "choyxonalar kerak",
    ]:
        return "Choyxonalar"

    if normalized in [
        "apteka",
        "aptekalar",
        "dorixona",
        "dorixonalar",
        "apteka kerak",
        "aptekalar kerak",
    ]:
        return "Aptekalar"

    return None


def is_advertisement(text):
    normalized = normalize(text)

    # Aniq reklama iboralari
    for word in AD_WORDS:
        if normalize(word) in normalized:
            return True

    # Juda ko'p xizmatlar ketma-ket sanab o'tilgan bo'lsa
    service_words = [
        "elektrik",
        "santexnika",
        "svarka",
        "gaz montaj",
        "suv montaj",
        "lyustra",
        "plafon",
        "avtomat",
        "antenna",
        "nasos",
        "o'rnatish",
        "ornatish",
        "ta'mirlash",
        "tamirlash",
    ]

    count = 0

    for word in service_words:
        if normalize(word) in normalized:
            count += 1

    if count >= 3:
        return True

    return False


def extract_name(text, phones):
    if not text:
        return "Nomi ko'rsatilmagan"

    name = text

    # Barcha telefonlarni nomdan olib tashlaymiz
    for phone in phones:
        name = name.replace(phone, "")
        name = name.replace(phone.replace("+", ""), "")

    # Emoji va keraksiz belgilarni tozalash
    name = re.sub(r"[📞☎️🔧🛠️📱⚡💧🔥🚿🚰💡📺📡🏗️👨🏻‍🏭]", " ", name)

    lines = []

    for line in name.splitlines():
        line = line.strip()

        if not line:
            continue

        if re.fullmatch(r"[\W_]+", line):
            continue

        lines.append(line)

    if not lines:
        return "Nomi ko'rsatilmagan"

    result = " ".join(lines)

    result = re.sub(r"\s+", " ", result)

    return result[:150]


# =========================================================
# SAQLASH
# =========================================================

def save_record(chat_id, category, name, phone, source_text):
    conn = get_db()

    # Bir xil raqam + bir xil kategoriya + bir xil nom takrorlanmasin
    existing = conn.execute("""
        SELECT id
        FROM records
        WHERE chat_id = ?
        AND category = ?
        AND name = ?
        AND phone = ?
        LIMIT 1
    """, (
        chat_id,
        category,
        name,
        phone
    )).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO records
            (chat_id, category, name, phone, source_text)
            VALUES (?, ?, ?, ?, ?)
        """, (
            chat_id,
            category,
            name,
            phone,
            source_text
        ))

        conn.commit()

    conn.close()


# =========================================================
# MAXSUS XIZMAT JAVOBI
# =========================================================

async def send_my_service(message):
    text = (
        "📞 Kerakli raqam:\n\n"
        f"1. {MY_PHONES[0]}\n"
        f"2. {MY_PHONES[1]}"
    )

    await message.reply_text(text)


# =========================================================
# KATEGORIYA QIDIRISH
# =========================================================

async def search_category(message, chat_id, category):
    conn = get_db()

    rows = conn.execute("""
        SELECT name, phone
        FROM records
        WHERE chat_id = ?
        AND category = ?
        ORDER BY name COLLATE NOCASE
    """, (
        chat_id,
        category
    )).fetchall()

    conn.close()

    if not rows:
        await message.reply_text(
            f"❌ {category} bo'yicha hozircha raqam topilmadi."
        )
        return

    result = f"📋 {category}\n\n"

    current_name = None

    for row in rows:
        name = row["name"]
        phone = row["phone"]

        if name != current_name:
            if current_name is not None:
                result += "\n"

            result += f"🏪 {name}\n"
            current_name = name

        result += f"📞 {phone}\n"

    # Telegram xabar chegarasidan oshib ketmasin
    if len(result) > 4000:
        result = result[:3900] + "\n\n…"

    await message.reply_text(result)


# =========================================================
# NOM BO'YICHA QIDIRISH
# =========================================================

async def search_name(message, chat_id, text):
    normalized = normalize(text)

    conn = get_db()

    rows = conn.execute("""
        SELECT category, name, phone
        FROM records
        WHERE chat_id = ?
        ORDER BY id DESC
    """, (
        chat_id,
    )).fetchall()

    conn.close()

    matches = []

    for row in rows:
        name = normalize(row["name"])

        if normalized in name or name in normalized:
            matches.append(row)

    if not matches:
        return False

    result = "🔎 Topildi:\n\n"

    for row in matches[:30]:
        result += (
            f"🏪 {row['name']}\n"
            f"📂 {row['category']}\n"
            f"📞 {row['phone']}\n\n"
        )

    await message.reply_text(result[:4000])

    return True


# =========================================================
# ASOSIY HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.effective_message

    if not message:
        return

    # Botning o'z xabarlarini qayta saqlamasin
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""

    if not text:
        return

    chat_id = message.chat_id

    # -----------------------------------------------------
    # REPLY BO'LSA: reply qilingan xabarni ham hisobga olamiz
    # -----------------------------------------------------

    reply_text = ""

    if message.reply_to_message:
        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )

    combined_text = text

    if reply_text:
        combined_text += "\n" + reply_text

    # -----------------------------------------------------
    # MAXSUS XIZMAT
    # -----------------------------------------------------

    if is_my_service(combined_text):

        # Agar odam aynan xizmatni so'rayotgan bo'lsa,
        # faqat bizning raqamlarni beramiz.
        #
        # Agar bu reklama bo'lsa, saqlamaymiz va javob bermaymiz.
        if is_advertisement(combined_text):
            return

        await send_my_service(message)
        return

    # -----------------------------------------------------
    # TELEFONLARNI TOPISH
    # -----------------------------------------------------

    phones = find_phones(combined_text)

    # -----------------------------------------------------
    # REKLAMA BO'LSA SAQLAMAYMIZ
    # -----------------------------------------------------

    if phones and is_advertisement(combined_text):
        return

    # -----------------------------------------------------
    # KATEGORIYA QIDIRUV
    # -----------------------------------------------------

    category_query = is_category_query(text)

    if category_query:
        await search_category(
            message,
            chat_id,
            category_query
        )
        return

    # -----------------------------------------------------
    # NOM BO'YICHA QIDIRUV
    # -----------------------------------------------------

    if not phones:
        found = await search_name(
            message,
            chat_id,
            text
        )

        if found:
            return

        return

    # -----------------------------------------------------
    # KATEGORIYANI ANIQLASH
    # -----------------------------------------------------

    category = detect_category(combined_text)

    if not category:
        category = "Boshqa"

    # -----------------------------------------------------
    # NOMNI ANIQLASH
    # -----------------------------------------------------

    name = extract_name(
        combined_text,
        phones
    )

    # -----------------------------------------------------
    # MAXSUS XIZMAT RAQAMLARINI BOSHQA ODAMLARNIKI
    # SAQLANMASLIGI
    # -----------------------------------------------------

    if is_my_service(combined_text):
        return

    # -----------------------------------------------------
    # HAR BIR TELEFONNI ALOHIDA SAQLAYMIZ
    # -----------------------------------------------------

    for phone in phones:

        save_record(
            chat_id=chat_id,
            category=category,
            name=name,
            phone=phone,
            source_text=combined_text
        )


# =========================================================
# BOTNI ISHGA TUSHIRISH
# =========================================================

def main():

    create_database()

    # Flask serverni alohida threadda ishga tushiramiz
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    # Telegram application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Oddiy text va caption xabarlarini qabul qiladi
    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.CaptionRegex(".+"),
            handle_message
        )
    )

    print("🚀 PRO BOT ISHLADI!")

    # Eski webhook bo'lsa tozalaydi
    # va pollingni boshlaydi
    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
