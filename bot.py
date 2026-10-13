import os
import re
import logging
import threading
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==============================
# SOZLAMALAR
# ==============================

load_dotenv(Path(__file__).with_name(".env"), override=True)

BOT_TOKEN = os.getenv("8924239590:AAGPy9pquTN-_zhebzGiCTQO7z_SEQ-xAno")
DATABASE_URL = os.getenv("postgresql://postgres.axcvpgkycofmmsbodfvv:GGykq23fSCo3nLVc@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env faylini tekshiring.")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi. .env faylini tekshiring.")


# ==============================
# MAXSUS XIZMATLAR
# Bu xizmatlarda boshqa raqam saqlanmaydi.
# ==============================

MY_NUMBERS = [
    "+998979600501",
    "+998911517577",
]

SPECIAL_SERVICES = {
    "konditsioner": [
        "konditsioner",
        "konditsaner",
        "kanditsioner",
        "kansaner",
        "кондиционер",
    ],
    "kotel": [
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
        "катёл",
        "котел",
        "котёл",
        "қозон",
    ],
    "santexnika": [
        "santexnik",
        "santexnika",
        "сантехник",
        "сантехника",
    ],
    "televizor": [
        "televizor",
        "televizor usta",
        "телевизор",
        "телевизор уста",
    ],
    "perforator": [
        "perforatorchi",
        "perfaratorchi",
        "perforator",
        "перфораторчи",
        "перфоратор",
    ],
    "kir_mashina": [
        "kirmashina",
        "kirmoshina",
        "kir yuvish mashinasi",
        "kir mashina",
        "avtomat",
        "stiralka",
        "стиралка",
        "стиральная машина",
        "кир ювиш машинаси",
    ],
}


# ==============================
# KATEGORIYALAR
# ==============================

CATEGORIES = {
    "aptekalar": [
        "apteka",
        "aptekalar",
        "аптека",
        "аптекалар",
        "dorixona",
        "dorixonalar",
    ],
    "choyxonalar": [
        "choyxona",
        "choyxonalar",
        "чайхона",
        "чайхоналар",
    ],
    "gril": [
        "gril",
        "гриль",
        "грил",
    ],
}


# ==============================
# HUDUDLAR
# ==============================

REGIONS = {
    "Navoiy": [
        "navoiy",
        "navoi",
        "навоий",
    ],
    "Charxiy": [
        "charxiy",
        "charhiy",
        "charxii",
        "чархий",
        "чархии",
    ],
    "Romanka": [
        "romanka",
        "романка",
    ],
    "Yangi bozor": [
        "yangi bozor",
        "yangibozor",
        "янги бозор",
        "янгибозор",
    ],
    "Salang": [
        "salang",
        "саланг",
    ],
    "Chodaklik": [
        "chodaklik",
        "чодаклик",
    ],
    "Sud": [
        "sud",
        "суд",
    ],
    "Vokzal": [
        "vokzal",
        "vagzal",
        "вокзал",
        "вагзал",
    ],
    "Ximik": [
        "ximik",
        "khimik",
        "химик",
    ],
    "Sorklet": [
        "sorklet",
        "сорклет",
    ],
    "Kalve": [
        "kalve",
        "калве",
    ],
    "Baqachorsu": [
        "baqachorsu",
        "bakachorsu",
        "бақачорсу",
        "бакачорсу",
    ],
    "Kosmonavt": [
        "kosmonavt",
        "kasmanavt",
        "kosmanavt",
        "космонавт",
        "касманавт",
    ],
}


# ==============================
# BRENDLAR
# ==============================

BRANDS = {
    "Artel": ["artel", "артел"],
    "Midea": ["midea", "мидеа"],
    "Samsung": ["samsung", "самсунг"],
    "LG": ["lg", "элджи"],
    "Gree": ["gree", "гри"],
    "Avalon": ["avalon", "авалон"],
    "Vaillant": [
        "vaillant",
        "vailant",
        "valiant",
        "vaylant",
        "вайлант",
    ],
    "Ariston": ["ariston", "аристон"],
    "Buderus": ["buderus", "будерус"],
    "Remexa": ["remexa", "ремекса"],
    "Airfel": ["airfel", "айрфел"],
    "Bosch": ["bosch", "бош"],
}


# ==============================
# MATNNI NORMALIZATSIYA QILISH
# ==============================

def normalize(text):
    text = (text or "").lower().strip()

    text = text.replace("ё", "е")
    text = text.replace("ў", "у")
    text = text.replace("ғ", "г")
    text = text.replace("қ", "к")
    text = text.replace("ҳ", "х")

    text = re.sub(r"[^\w\s+]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def find_alias(text, groups):
    text = normalize(text)

    for canonical, aliases in groups.items():
        for alias in aliases:
            alias = normalize(alias)

            if re.search(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                text,
            ):
                return canonical

    return None


def find_special_service(text):
    text = normalize(text)

    for service, aliases in SPECIAL_SERVICES.items():
        for alias in aliases:
            alias = normalize(alias)

            if re.search(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                text,
            ):
                return service

    return None


def get_region(text):
    return find_alias(text, REGIONS)


def get_brand(text):
    return find_alias(text, BRANDS)


def get_category(text):
    return find_alias(text, CATEGORIES)


# ==============================
# TELEFON RAQAMLARINI TOPISH
# ==============================

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?998[\s().-]*)?"
    r"(?:\d[\s().-]*){9}(?!\d)"
)


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)

    if len(digits) == 9:
        digits = "998" + digits

    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits

    return None


def extract_phones(text):
    result = []

    for match in PHONE_PATTERN.findall(text or ""):
        phone = normalize_phone(match)

        if phone and phone not in result:
            result.append(phone)

    return result


# ==============================
# MA'LUMOTLAR BAZASI
# ESKI YOZUVLAR O'CHIRILMAYDI
# ==============================

def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=15,
    )


def ensure_database():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE public.records
                ADD COLUMN IF NOT EXISTS region TEXT
            """)

            cur.execute("""
                ALTER TABLE public.records
                ADD COLUMN IF NOT EXISTS brand TEXT
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                records_category_idx
                ON public.records (category)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                records_name_idx
                ON public.records (name)
            """)

        conn.commit()

    logger.info("Ma'lumotlar bazasi tekshirildi.")


# ==============================
# E'LONNI QAYDGA AJRATISH
#
# Kutiladigan shakl:
# 📂 Choyxonalar
# 🏷 Farovon choyxona
# 📞 +998...
# 📞 +998...
# ==============================

def parse_records(text):
    if not text:
        return []

    # Faqat tuzilgan katalog xabarlarini qabul qilamiz.
    # Oddiy reklama va erkin matn avtomatik saqlanmaydi.
    if "🏷" not in text and "📂" not in text:
        return []

    lines = text.splitlines()
    current_category = None
    current_name = None
    current_phones = []
    records = []

    def save_current():
        nonlocal current_category, current_name, current_phones

        if current_category and current_name and current_phones:
            records.append({
                "category": current_category,
                "name": current_name.strip(),
                "phones": list(dict.fromkeys(current_phones)),
            })

        current_name = None
        current_phones = []

    for line in lines:
        line = line.strip()

        if line.startswith("📂"):
            save_current()
            current_category = line.replace("📂", "", 1).strip()
            continue

        if line.startswith("🏷"):
            save_current()
            current_name = line.replace("🏷", "", 1).strip()
            continue

        if line.startswith("📞"):
            if current_name:
                current_phones.extend(extract_phones(line))
            continue

    save_current()

    # Maxsus xizmatlar kategoriyasidagi raqamlar
    # bazaga yozilmaydi.
    filtered = []

    for record in records:
        category_and_name = (
            record["category"] + " " + record["name"]
        )

        if find_special_service(category_and_name):
            continue

        valid_phones = [
            p for p in record["phones"]
            if p not in MY_NUMBERS
        ]

        if not valid_phones:
            continue

        record["phones"] = valid_phones
        filtered.append(record)

    return filtered


# ==============================
# FAQAT GURUH ADMINLARI SAQLAYDI
# ==============================

async def is_admin(update):
    if not update.effective_chat or not update.effective_user:
        return False

    if update.effective_chat.type not in ("group", "supergroup"):
        return False

    try:
        member = await update.effective_chat.get_member(
            update.effective_user.id
        )

        return member.status in ("administrator", "creator")

    except Exception:
        logger.exception("Admin holatini tekshirishda xato")
        return False


async def save_group_records(update):
    message = update.effective_message

    if not message or not message.text:
        return

    if not await is_admin(update):
        return

    parsed = parse_records(message.text)

    if not parsed:
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                for record in parsed:
                    category = (
                        get_category(record["category"])
                        or record["category"].strip()
                        or "Boshqa"
                    )

                    region = get_region(
                        record["name"] + " " + record["category"]
                    )

                    brand = get_brand(
                        record["name"] + " " + record["category"]
                    )

                    for phone in record["phones"]:
                        cur.execute("""
                            SELECT id
                            FROM public.records
                            WHERE category = %s
                              AND name = %s
                              AND phone = %s
                            LIMIT 1
                        """, (
                            category,
                            record["name"],
                            phone,
                        ))

                        if cur.fetchone():
                            continue

                        cur.execute("""
                            INSERT INTO public.records
                            (
                                category,
                                name,
                                phone,
                                source_text,
                                chat_id,
                                user_id,
                                region,
                                brand
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            category,
                            record["name"],
                            phone,
                            message.text,
                            update.effective_chat.id,
                            update.effective_user.id,
                            region,
                            brand,
                        ))

            conn.commit()

        logger.info("Admin katalog yozuvlari tekshirildi va saqlandi.")

    except Exception:
        logger.exception("Ma'lumotni saqlashda xato")


# ==============================
# QIDIRUV
# ==============================

def get_all_records():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    id,
                    category,
                    name,
                    phone,
                    region,
                    brand
                FROM public.records
                ORDER BY category, name, id
            """)

            return cur.fetchall()


def remove_aliases_from_query(query):
    result = normalize(query)

    all_groups = [CATEGORIES, REGIONS, BRANDS]

    for group in all_groups:
        for aliases in group.values():
            for alias in aliases:
                alias = normalize(alias)

                result = re.sub(
                    r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                    " ",
                    result,
                )

    for aliases in SPECIAL_SERVICES.values():
        for alias in aliases:
            alias = normalize(alias)

            result = re.sub(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
                " ",
                result,
            )

    result = re.sub(r"\s+", " ", result).strip()
    return result


def search_records(query):
    query_normalized = normalize(query)

    # Maxsus xizmatlarda faqat o'z raqamlarimiz.
    special_service = find_special_service(query_normalized)

    if special_service:
        labels = {
            "konditsioner": "Konditsioner ustasi",
            "kotel": "Katyol / qozon ustasi",
            "santexnika": "Santexnik",
            "televizor": "Televizor ustasi",
            "perforator": "Perforator xizmati",
            "kir_mashina": "Kir yuvish mashinasi ustasi",
        }

        return {
            "title": labels[special_service],
            "special": True,
            "records": [{
                "category": labels[special_service],
                "name": "Boburjon — xizmat",
                "phones": MY_NUMBERS,
            }],
        }

    category = get_category(query_normalized)
    region = get_region(query_normalized)
    brand = get_brand(query_normalized)

    remaining = remove_aliases_from_query(query_normalized)

    try:
        rows = get_all_records()
    except Exception:
        logger.exception("Qidiruv vaqtida ma'lumotlar bazasi xatosi")
        return None

    matches = []

    for row in rows:
        row_category = normalize(row["category"])
        row_name = normalize(row["name"])
        row_region = normalize(row.get("region"))
        row_brand = normalize(row.get("brand"))

        if category and row_category != normalize(category):
            continue

        if region:
            # Faqat aniq belgilangan hudud mos kelsin.
            if row_region and row_region != normalize(region):
                continue

            if not row_region and normalize(region) not in row_name:
                continue

        if brand:
            if row_brand and row_brand != normalize(brand):
                continue

            if not row_brand and normalize(brand) not in row_name:
                continue

        if remaining:
            # Joy nomi so'rovdagi qolgan matnga mos kelishi kerak.
            if remaining not in row_name:
                continue

        matches.append(row)

    if not matches:
        return {
            "title": query,
            "special": False,
            "records": [],
        }

    # Bir joyning bir nechta raqamini bitta guruhga yig'amiz.
    grouped = {}

    for row in matches:
        key = (
            row["category"],
            row["name"],
        )

        if key not in grouped:
            grouped[key] = {
                "category": row["category"],
                "name": row["name"],
                "phones": [],
            }

        phone = row["phone"]

        if phone and phone not in grouped[key]["phones"]:
            grouped[key]["phones"].append(phone)

    return {
        "title": category or query,
        "special": False,
        "records": list(grouped.values()),
    }


# ==============================
# JAVOBNI YUBORISH
# ==============================

def format_results(result):
    if result is None:
        return "Ma'lumotlar bazasiga ulanishda xato yuz berdi."

    records = result["records"]

    if not records:
        return (
            "❌ Bu nom bo'yicha raqam topilmadi.\n\n"
            "Joy nomini boshqacha yozib ko'ring."
        )

    output = []

    for record in records:
        output.append(f"📂 {record['category']}")
        output.append(f"🏷 {record['name']}")

        for phone in record["phones"]:
            output.append(f"📞 {phone}")

        output.append("")

    return "\n".join(output).strip()


async def reply_in_chunks(message, text):
    max_length = 3500

    while text:
        if len(text) <= max_length:
            await message.reply_text(text)
            break

        split_at = text.rfind("\n", 0, max_length)

        if split_at <= 0:
            split_at = max_length

        part = text[:split_at]
        text = text[split_at:].lstrip("\n")

        await message.reply_text(part)


# ==============================
# XABARLARNI QABUL QILISH
# ==============================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text:
        return

    chat = update.effective_chat

    if not chat:
        return

    # Guruhdagi admin xabarlari katalog yozuvi bo'lishi
    # mumkin. Oddiy foydalanuvchi ma'lumot qo'sha olmaydi.
    if chat.type in ("group", "supergroup"):
        await save_group_records(update)

    # Bot o'z xabarlariga javob bermaydi.
    if update.effective_user and update.effective_user.is_bot:
        return

    query = message.text.strip()

    # Katalog ko'rinishidagi ma'lumot yuborilsa,
    # uni oddiy qidiruv sifatida qayta ishlamaymiz.
    if "🏷" in query and "📂" in query:
        return

    # Qidiruv natijasini oddiy matnli so'rov uchun chiqaramiz.
    result = search_records(query)
    answer = format_results(result)

    await reply_in_chunks(message, answer)


# ==============================
# RENDER UCHUN WEB SERVER
# ==============================

web_app = Flask(__name__)


@web_app.get("/")
def home():
    return "Kerakli raqamlar PRO ishlayapti."


@web_app.get("/health")
def health():
    return {"status": "ok"}


def run_web():
    port = int(os.getenv("PORT", "10000"))

    web_app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# ==============================
# BOTNI ISHGA TUSHIRISH
# ==============================

def main():
    ensure_database()

    threading.Thread(
        target=run_web,
        daemon=True,
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Kerakli raqamlar PRO ishga tushmoqda.")

    application.run_polling(
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
