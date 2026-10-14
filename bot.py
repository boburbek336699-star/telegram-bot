import os
import re
import logging
import asyncio
import unicodedata
from datetime import datetime

import asyncpg
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)


# ==================================================
# 1. SOZLAMALAR
# ==================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

SOURCE_CHAT = os.getenv(
    "SOURCE_CHAT",
    "@KERAKLI_RAQAMLAR1"
).strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylida topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL .env faylida topilmadi!")


# ==================================================
# 2. LOG
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("KRP")


# ==================================================
# 3. YASMINA SHOPPING REKLAMASI
# ==================================================

SHOPPING_BLOCK = """
━━━━━━━━━━━━━━
🛍 YASMINA SHOPPING 🛍
💖 Ayollar uchun ajoyib mahsulotlar!

👉 https://t.me/yasmina_shooooping
━━━━━━━━━━━━━━
"""


# ==================================================
# 4. MAXSUS XIZMATLAR
# ==================================================

MY_NUMBERS = [
    "+998911517577",
    "+998979600501",
]

SPECIAL_SERVICES = {
    "konditsioner": [
        "konditsioner",
        "konditsaner",
        "kanditsaner",
        "konditsionerchi",
        "konditsioner usta",
        "кондиционер",
        "кондиционер уста",
        "konditsioner tamirlash",
        "konditsioner tuzatish",
        "freon",
    ],

    "katyol": [
        "katyol",
        "kotel",
        "qozon",
        "gaz qozon",
        "vaillant",
        "vailant",
        "vaylant",
        "вайлант",
        "котел",
        "котёл",
        "газовый котел",
        "katyol usta",
    ],

    "kir_mashina": [
        "kirmoshina",
        "kir moshina",
        "kir mashina",
        "kir yuvish mashinasi",
        "стиральная машина",
        "стиралка",
        "kir mashina usta",
    ],

    "perforator": [
        "perforator",
        "perfarator",
        "perforator usta",
        "beton teshish",
        "бетон тешиш",
    ],

    "santexnik": [
        "santexnik",
        "santexnika",
        "santehnik",
        "сантехник",
        "сантехника",
        "truba usta",
        "suv quvuri",
    ],

    "televizor": [
        "televizor",
        "telivizor",
        "televizor usta",
        "телевизор",
        "tv tamirlash",
    ],
}

SPECIAL_TITLES = {
    "konditsioner": "❄️ KONDITSIONER USTASI",
    "katyol": "🔥 KATYOL VA GAZ QOZON USTASI",
    "kir_mashina": "🧺 KIR YUVISH MASHINASI USTASI",
    "perforator": "🔨 PERFORATOR VA BETON TESHISH",
    "santexnik": "🔧 SANTEXNIK XIZMATI",
    "televizor": "📺 TELEVIZOR TA'MIRLASH",
}


# ==================================================
# 5. MATNNI NORMAL HOLATGA KELTIRISH
# ==================================================

CYRILLIC_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g",
    "д": "d", "е": "e", "ё": "yo", "ж": "j",
    "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "s",
    "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "", "ы": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
})


def normalize_text(text):
    text = (text or "").lower()

    text = text.replace("ў", "o")
    text = text.replace("ғ", "g")
    text = text.replace("қ", "q")
    text = text.replace("ҳ", "h")

    text = text.translate(CYRILLIC_MAP)

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(r"[^a-z0-9+]+", " ", text)

    return " ".join(text.split())


# ==================================================
# 6. TELEFON RAQAMLARINI TOPISH
# ==================================================

PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\+?998[\s().-]*\d{2}|0\d{2}|\d{2})"
    r"(?:[\s().-]*\d){7}"
    r"(?!\d)"
)


def extract_phones(text):
    found = []

    for match in PHONE_PATTERN.finditer(text or ""):
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)

        if digits.startswith("998") and len(digits) == 12:
            phone = "+" + digits

        elif digits.startswith("0") and len(digits) == 10:
            phone = "+998" + digits[1:]

        elif len(digits) == 9:
            phone = "+998" + digits

        else:
            continue

        if phone not in found:
            found.append(phone)

    return found


# ==================================================
# 7. XIZMAT VA HUDUDNI ANIQLASH
# ==================================================

CATEGORY_WORDS = {
    "apteka": [
        "apteka", "dorixona", "dorixona raqami",
        "аптека", "dorilar",
    ],
    "shifokor": [
        "doktor", "doctor", "shifokor",
        "vrach", "табиб", "врач",
    ],
    "usta": [
        "usta", "ustasi", "tamirlash",
        "ta'mirlash", "tuzatish", "ремонт",
    ],
    "tozalash": [
        "tozalash", "tozalovchi", "farrosh",
        "уборка", "уборщица",
    ],
    "karcher": [
        "karcher", "karcher usta",
        "kercher", "karcher yuvish",
    ],
    "gush": [
        "gush", "gusht", "gush markazi",
        "go'sht", "gosht",
    ],
}


LOCATIONS = [
    "navoiy",
    "charxiy",
    "romanka",
    "yangi bozor",
    "salang",
    "salen",
    "chodaklik",
    "sud",
    "vokzal",
    "ximik",
    "sorklet",
    "kalve",
    "baqachorsu",
    "kosmonavt",
    "gishkoprik",
]


def detect_category(text):
    normalized = normalize_text(text)

    for category, words in CATEGORY_WORDS.items():
        for word in words:
            if normalize_text(word) in normalized:
                return category

    for service, words in SPECIAL_SERVICES.items():
        for word in words:
            if normalize_text(word) in normalized:
                return service

    return "boshqa"


def detect_location(text):
    normalized = normalize_text(text)

    for location in LOCATIONS:
        if normalize_text(location) in normalized:
            return location

    return ""


def detect_brand(text):
    normalized = normalize_text(text)

    brands = [
        "artel", "lg", "samsung", "midea", "bosch",
        "vaillant", "vailant", "remexa", "remeha",
        "buderus", "ariston", "airfel", "baymak",
        "gree", "aux", "chigo", "avalon",
    ]

    for brand in brands:
        if normalize_text(brand) in normalized:
            return brand

    return ""


def detect_organization(text, phone):
    """
    Telefon oldidagi matndan ehtiyotkorlik bilan nom ajratadi.
    Aniq nom topilmasa, asl matn saqlanadi.
    """

    text_before = (text or "").split(phone)[0].strip()

    text_before = re.sub(
        r"^[\s📞☎️🏷️📱:;,\-]+",
        "",
        text_before,
    )

    lines = [
        line.strip()
        for line in text_before.splitlines()
        if line.strip()
    ]

    if lines:
        candidate = lines[-1]

        if len(candidate) >= 3:
            return candidate[:200]

    return "Nomi aniqlanmagan"


# ==================================================
# 8. SUPABASE BAZASIGA ULANISH
# ==================================================

db_pool = None


async def init_database():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=20,
    )

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS krp_records (
                id BIGSERIAL PRIMARY KEY,
                organization TEXT,
                phone TEXT,
                category TEXT,
                location TEXT,
                brand TEXT,
                original_text TEXT,
                source_chat TEXT,
                source_message_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS
            krp_records_phone_idx
            ON krp_records(phone)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS
            krp_records_category_idx
            ON krp_records(category)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS
            krp_records_location_idx
            ON krp_records(location)
        """)

    log.info("Supabase bazasiga ulanish muvaffaqiyatli.")


# ==================================================
# 9. GURUH XABARLARINI SAQLASH
# ==================================================

async def save_source_message(
    text,
    chat_id,
    message_id,
    chat_title="",
):
    phones = extract_phones(text)

    if not phones:
        log.info(
            "Manba xabari olindi, lekin raqam topilmadi. "
            "Xabar ID: %s",
            message_id,
        )
        return

    category = detect_category(text)
    location = detect_location(text)
    brand = detect_brand(text)

    async with db_pool.acquire() as conn:
        for phone in phones:
            organization = detect_organization(text, phone)

            # Bir xil xabar qayta kelgan bo'lsa,
            # ayni yozuvni qayta qo'shmaymiz.
            exists = await conn.fetchval("""
                SELECT id
                FROM krp_records
                WHERE source_chat = $1
                  AND source_message_id = $2
                  AND phone = $3
                LIMIT 1
            """, str(chat_id), message_id, phone)

            if exists:
                continue

            await conn.execute("""
                INSERT INTO krp_records (
                    organization,
                    phone,
                    category,
                    location,
                    brand,
                    original_text,
                    source_chat,
                    source_message_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    NOW(), NOW()
                )
            """,
                organization,
                phone,
                category,
                location,
                brand,
                text,
                str(chat_id),
                message_id,
            )

    log.info(
        "MANBA XABARI SAQLANDI | chat=%s | message=%s | raqamlar=%s",
        chat_title or chat_id,
        message_id,
        ", ".join(phones),
    )


# ==================================================
# 10. MAXSUS XIZMATNI TOPISH
# ==================================================

def find_special(text):
    normalized = normalize_text(text)

    for service, words in SPECIAL_SERVICES.items():
        for word in words:
            normalized_word = normalize_text(word)

            if normalized_word and normalized_word in normalized:
                return service, {
                    "title": SPECIAL_TITLES[service]
                }

    return None, None


# ==================================================
# 11. BAZADAN QIDIRISH
# ==================================================

async def search_records(query):
    normalized_query = normalize_text(query)

    if not normalized_query:
        return []

    query_words = [
        word for word in normalized_query.split()
        if len(word) >= 2
    ]

    if not query_words:
        return []

    async with db_pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT
                id,
                organization,
                phone,
                category,
                location,
                brand,
                original_text,
                source_chat,
                source_message_id
            FROM krp_records
            ORDER BY updated_at DESC
            LIMIT 3000
        """)

    scored = []

    requested_location = detect_location(query)

    for row in records:
        searchable = " ".join([
            str(row["organization"] or ""),
            str(row["phone"] or ""),
            str(row["category"] or ""),
            str(row["location"] or ""),
            str(row["brand"] or ""),
            str(row["original_text"] or ""),
        ])

        normalized_record = normalize_text(searchable)

        # Hudud aniq so'ralgan bo'lsa,
        # boshqa hudud yozuvlarini chiqarmaymiz.
        if requested_location:
            record_location = normalize_text(
                row["location"] or ""
            )

            original_location = normalize_text(
                row["original_text"] or ""
            )

            if (
                requested_location not in record_location
                and requested_location not in original_location
            ):
                continue

        score = 0

        for word in query_words:
            if word in normalized_record:
                score += 1

        # So'rovdagi muhim so'zlarning hammasi
        # topilmagan bo'lsa, natijani chiqarishga shoshilmaymiz.
        if score == 0:
            continue

        if len(query_words) >= 2 and score < 2:
            continue

        if normalized_query in normalized_record:
            score += 3

        if row["phone"]:
            score += 1

        scored.append((score, row))

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # Bir tashkilotning takroriy raqamini
    # bir javobda qayta-qayta ko'rsatmaymiz.
    results = []
    seen = set()

    for score, row in scored:
        phone = row["phone"]

        if not phone or phone in seen:
            continue

        seen.add(phone)
        results.append(row)

        if len(results) >= 10:
            break

    return results


# ==================================================
# 12. JAVOBNI TAYYORLASH
# ==================================================

def format_results(rows):
    blocks = []

    for row in rows:
        organization = (
            row["organization"] or "Nomi aniqlanmagan"
        )

        phone = row["phone"] or ""

        category = row["category"] or ""
        location = row["location"] or ""
        brand = row["brand"] or ""

        block = (
            f"🏷 {organization}\n"
            f"📞 {phone}"
        )

        if category and category != "boshqa":
            block += f"\n📂 Xizmat: {category}"

        if location:
            block += f"\n📍 Hudud: {location}"

        if brand:
            block += f"\n🏷 Brend: {brand}"

        blocks.append(block)

    if not blocks:
        return ""

    return (
        "\n\n━━━━━━━━━━━━━━\n\n".join(blocks)
        + "\n\n"
        + SHOPPING_BLOCK
    )


async def send_reply(update, text):
    message = update.effective_message

    if not message or not text:
        return

    await message.reply_text(
        text,
        disable_web_page_preview=True,
    )


# ==================================================
# 13. ASOSIY XABAR QABUL QILISH
# ==================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    text = message.text or message.caption or ""

    if not text.strip():
        return

    if message.from_user and message.from_user.is_bot:
        return

    # Manba guruhdagi xabarlarni saqlash
    source_username = SOURCE_CHAT.lstrip("@").lower()
    chat_username = (
        getattr(chat, "username", None) or ""
    ).lower()

    is_group = chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    )

    is_source = (
        is_group
        and (
            (
                SOURCE_CHAT.startswith("@")
                and chat_username == source_username
            )
            or str(chat.id) == SOURCE_CHAT
        )
    )

    if is_source:
        try:
            await save_source_message(
                text=text,
                chat_id=chat.id,
                message_id=message.message_id,
                chat_title=chat.title or "",
            )
        except Exception:
            log.exception(
                "Manba guruhidagi xabarni saqlashda xato"
            )

        # Manba guruhida bot qidiruv javobini bermaydi.
        return

    # Maxsus xizmatlar
    service, special = find_special(text)

    if service and special:
        answer = (
            special["title"]
            + "\n\n"
            + "\n".join(
                f"📞 {number}"
                for number in MY_NUMBERS
            )
            + "\n\n"
            + "✅ Tez • Sifatli • Ishonchli"
            + "\n\n"
            + SHOPPING_BLOCK
        )

        try:
            await send_reply(update, answer)
        except Exception:
            log.exception("Maxsus xizmat javobida xato")

        return

    # Oddiy qidiruv
    try:
        rows = await search_records(text)

        if not rows:
            log.info(
                "Raqam topilmadi. Javob yuborilmadi."
            )
            return

        answer = format_results(rows)

        if answer:
            await send_reply(update, answer)

    except Exception:
        log.exception("Qidiruvda xato")
        return


# ==================================================
# 14. BOT ISHGA TUSHISHI
# ==================================================

async def post_init(application):
    await init_database()
    log.info("Kerakli Raqamlar PRO ishga tayyor.")


async def post_shutdown(application):
    global db_pool

    if db_pool:
        await db_pool.close()
        db_pool = None


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT | filters.CAPTION,
            handle_message,
        )
    )

    log.info("Bot ishga tushmoqda...")

    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=["message"],
    )


if __name__ == "__main__":
    main()
