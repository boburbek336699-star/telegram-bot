import os
import re
import logging
import threading
from pathlib import Path
from functools import lru_cache

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


# ==================================================
# SOZLAMALAR
# ==================================================

load_dotenv(Path(__file__).with_name(".env"), override=False)

BOT_TOKEN = os.getenv("8924239590:AAHxRHY_AOfd7KG8ZvnUKKTyw_ZnoSxiXCs")
DATABASE_URL = os.getenv("postgresql://postgres.axcvpgkycofmmsbodfvv:bobur336699bek@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Render Environment sozlamasini tekshiring."
    )

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL topilmadi. Supabase ulanish manzilini tekshiring."
    )


# ==================================================
# MAXSUS XIZMATLAR
# BU XIZMATLARDA FAQAT O'Z RAQAMLARINGIZ
# ==================================================

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
        "konditsionerchi",
        "кондиционер",
    ],
    "kotel": [
        "katyol",
        "katel",
        "kotel",
        "qozon",
        "gaz qozon",
        "katyol qozon",
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


SPECIAL_LABELS = {
    "konditsioner": "Konditsioner ustasi",
    "kotel": "Katyol / qozon ustasi",
    "santexnika": "Santexnik",
    "televizor": "Televizor ustasi",
    "perforator": "Perforator xizmati",
    "kir_mashina": "Kir yuvish mashinasi ustasi",
}


# ==================================================
# KATEGORIYALAR
# ==================================================

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


# ==================================================
# HUDUDLAR
# ==================================================

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


# ==================================================
# BRENDLAR
# ==================================================

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


# ==================================================
# MATNNI NORMALIZATSIYA QILISH
# ==================================================

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


def contains_alias(text, alias):
    text = normalize(text)
    alias = normalize(alias)

    if not text or not alias:
        return False

    return bool(
        re.search(
            r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
            text,
        )
    )


def find_alias(text, groups):
    for canonical, aliases in groups.items():
        for alias in aliases:
            if contains_alias(text, alias):
                return canonical

    return None


def find_special_service(text):
    text = normalize(text)

    # Uzunroq nomlar avval tekshiriladi.
    services = sorted(
        SPECIAL_SERVICES.items(),
        key=lambda item: max(
            len(normalize(alias))
            for alias in item[1]
        ),
        reverse=True,
    )

    for service, aliases in services:
        for alias in aliases:
            if contains_alias(text, alias):
                return service

    return None


def get_region(text):
    return find_alias(text, REGIONS)


def get_brand(text):
    return find_alias(text, BRANDS)


def get_category(text):
    return find_alias(text, CATEGORIES)


# ==================================================
# TELEFON RAQAMLARI
# ==================================================

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?998[\s().-]*)?"
    r"(?:\d[\s().-]*){9}(?!\d)"
)


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone or "")

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


# ==================================================
# MA'LUMOTLAR BAZASI
# MAVJUD MA'LUMOTLAR O'CHIRILMAYDI
# ==================================================

def get_connection():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=15,
        sslmode="require",
        application_name="kerakli_raqamlar_pro",
    )


def ensure_database():
    """
    Jadval bo'lmasa yaratadi.
    Jadval mavjud bo'lsa, kerakli ustunlarni qo'shadi.
    Mavjud yozuvlarni o'chirmaydi.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.records (
                    id BIGSERIAL PRIMARY KEY,
                    category TEXT,
                    name TEXT,
                    phone TEXT,
                    source_text TEXT,
                    chat_id BIGINT,
                    user_id BIGINT,
                    region TEXT,
                    brand TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Eski jadvalda ayrim ustunlar yo'q bo'lsa,
            # ularni bittalab qo'shamiz.

            columns = {
                "id": "BIGSERIAL",
                "category": "TEXT",
                "name": "TEXT",
                "phone": "TEXT",
                "source_text": "TEXT",
                "chat_id": "BIGINT",
                "user_id": "BIGINT",
                "region": "TEXT",
                "brand": "TEXT",
                "created_at": "TIMESTAMPTZ DEFAULT NOW()",
            }

            for column, column_type in columns.items():
                cur.execute(
                    f"""
                    ALTER TABLE public.records
                    ADD COLUMN IF NOT EXISTS {column} {column_type}
                    """
                )

            cur.execute("""
                CREATE INDEX IF NOT EXISTS records_category_idx
                ON public.records (category)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS records_name_idx
                ON public.records (name)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS records_region_idx
                ON public.records (region)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS records_brand_idx
                ON public.records (brand)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS records_phone_idx
                ON public.records (phone)
            """)

        conn.commit()

    logger.info("Ma'lumotlar bazasi tekshirildi.")


# ==================================================
# KATALOG XABARLARINI AJRATISH
# ==================================================

def parse_records(text):
    if not text:
        return []

    if "🏷" not in text and "📂" not in text:
        return []

    lines = text.splitlines()

    current_category = None
    current_name = None
    current_phones = []

    records = []

    def save_current():
        nonlocal current_name, current_phones

        if current_category and current_name and current_phones:
            records.append({
                "category": current_category.strip(),
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

        if line.startswith("📞") and current_name:
            current_phones.extend(extract_phones(line))

    save_current()

    filtered = []

    for record in records:
        category_and_name = (
            record["category"] + " " + record["name"]
        )

        # Maxsus xizmatlar uchun begona raqam saqlanmaydi.
        if find_special_service(category_and_name):
            continue

        valid_phones = [
            phone
            for phone in record["phones"]
            if phone not in MY_NUMBERS
        ]

        if not valid_phones:
            continue

        record["phones"] = valid_phones
        filtered.append(record)

    return filtered


# ==================================================
# GURUH ADMINLARINI TEKSHIRISH
# ==================================================

async def is_admin(update: Update):
    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return False

    if chat.type not in ("group", "supergroup"):
        return False

    try:
        member = await chat.get_member(user.id)

        return member.status in ("administrator", "creator")

    except Exception:
        logger.exception("Admin holatini tekshirishda xato")
        return False


# ==================================================
# KATALOG MA'LUMOTLARINI SAQLASH
# ==================================================

async def save_group_records(update: Update):
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

                    # Hudud va brend faqat aniq alias topilsa belgilanadi.
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
                            INSERT INTO public.records (
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

        logger.info("Katalog yozuvlari tekshirildi va saqlandi.")

    except Exception:
        logger.exception("Ma'lumotni saqlashda xato")


# ==================================================
# MA'LUMOTLARNI OLISH
# ==================================================

@lru_cache(maxsize=1)
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

            return tuple(dict(row) for row in cur.fetchall())


def refresh_records_cache():
    get_all_records.cache_clear()


# ==================================================
# SO'ROVDAN KERAKSIZ SO'ZLARNI OLIB TASHLASH
# ==================================================

GENERIC_WORDS = {
    "raqam",
    "raqami",
    "nomer",
    "nomeri",
    "telefon",
    "tel",
    "kerak",
    "bormi",
    "bering",
    "ber",
    "topib",
    "qidir",
    "qidiruv",
    "usta",
    "ustasi",
    "xizmat",
    "xizmati",
    "qayerda",
    "manzil",
    "iltimos",
    "menga",
    "uchun",
    "ni",
    "va",
    "ham",
}


def remove_aliases_from_query(query):
    result = normalize(query)

    all_groups = [
        CATEGORIES,
        REGIONS,
        BRANDS,
        SPECIAL_SERVICES,
    ]

    aliases = []

    for group in all_groups:
        for values in group.values():
            aliases.extend(values)

    # Uzun aliaslar birinchi olib tashlanadi.
    aliases.sort(key=lambda value: len(normalize(value)), reverse=True)

    for alias in aliases:
        alias = normalize(alias)

        result = re.sub(
            r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
            " ",
            result,
        )

    words = [
        word
        for word in result.split()
        if word not in GENERIC_WORDS
    ]

    return " ".join(words).strip()


# ==================================================
# QIDIRUV
# ==================================================

def search_records(query):
    query_normalized = normalize(query)

    # Maxsus xizmatlar uchun faqat o'z raqamlarimiz.
    special_service = find_special_service(query_normalized)

    if special_service:
        label = SPECIAL_LABELS[special_service]

        return {
            "title": label,
            "special": True,
            "records": [{
                "category": label,
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
        logger.exception("Qidiruvda ma'lumotlar bazasi xatosi")
        return None

    remaining_words = set(remaining.split())
    matches = []

    for row in rows:

        row_category = normalize(row.get("category"))
        row_name = normalize(row.get("name"))
        row_region = normalize(row.get("region"))
        row_brand = normalize(row.get("brand"))

        full_name = row_name

        # Kategoriya filtri.
        if category:
            if row_category != normalize(category):
                continue

        # Hudud filtri.
        if region:
            if row_region:
                if row_region != normalize(region):
                    continue
            elif not contains_alias(full_name, region):
                continue

        # Brend filtri.
        if brand:
            if row_brand:
                if row_brand != normalize(brand):
                    continue
            elif not contains_alias(full_name, brand):
                continue

        # Qolgan so'zlar joy nomiga moslashtiriladi.
        if remaining_words:
            name_words = set(full_name.split())

            matched_words = remaining_words & name_words

            # So'rov so'zlarining kamida yarmi mos kelishi kerak.
            required = max(
                1,
                (len(remaining_words) + 1) // 2,
            )

            if len(matched_words) < required:
                continue

        matches.append(row)

    if not matches:
        return {
            "title": query,
            "special": False,
            "records": [],
        }

    # Bitta joyning raqamlarini bir guruhga yig'amiz.
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


# ==================================================
# NATIJANI MATNGA AYLANTIRISH
# ==================================================

def format_results(result):
    if result is None:
        return (
            "⚠️ Ma'lumotlar bazasiga ulanishda xato yuz berdi.\n"
            "Birozdan keyin qayta urinib ko'ring."
        )

    records = result["records"]

    if not records:
        return (
            "❌ Bu so'rov bo'yicha raqam topilmadi.\n\n"
            "Boshqa nom, hudud yoki brend bilan qidirib ko'ring."
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


# ==================================================
# XABARLARNI QABUL QILISH
# ==================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat or not user:
        return

    if user.is_bot:
        return

    query = message.text.strip()

    # Katalog shaklidagi xabarni qayta ishlaymiz.
    if "🏷" in query or "📂" in query:

        if chat.type in ("group", "supergroup"):
            await save_group_records(update)
            refresh_records_cache()

        # Katalog xabari qidiruvga yuborilmaydi.
        return

    # Oddiy matnli so'rov.
    try:
        result = search_records(query)
        answer = format_results(result)

        await reply_in_chunks(message, answer)

    except Exception:
        logger.exception("Xabarni qayta ishlashda xato")

        try:
            await message.reply_text(
                "⚠️ Xatolik yuz berdi. Qayta urinib ko'ring."
            )
        except Exception:
            logger.exception("Xatolik xabarini yuborib bo'lmadi")


# ==================================================
# RENDER WEB SERVER
# ==================================================

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
        threaded=True,
    )


# ==================================================
# BOTNI ISHGA TUSHIRISH
# ==================================================

def main():
    ensure_database()

    threading.Thread(
        target=run_web,
        daemon=True,
        name="web-server",
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
