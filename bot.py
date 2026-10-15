import os
import re
import asyncio
import logging
import unicodedata
from datetime import datetime, timezone

import asyncpg
import httpx
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ChatType
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# =====================================================
# SOZLAMALAR
# =====================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

FOOTER = (
    "\n\n━━━━━━━━━━━━━━\n"
    "🛍 YASMINA SHOPPING 🛍\n"
    "💖 Ayollar uchun ajoyib mahsulotlar!\n\n"
    "👉 https://t.me/yasmina_shooooping\n"
    "━━━━━━━━━━━━━━"
)

MY_NUMBERS = [
    "+998911517577",
    "+998979600501",
]

# Maxsus xizmatlar: bular uchrasa, faqat o'z raqamlaringiz qaytariladi.
SPECIAL_SERVICES = {
    "konditsioner": [
        "konditsioner", "konditsaner", "kanditsioner",
        "kansaner", "кондиционер", "кондиционерчи",
    ],
    "katyol": [
        "katyol", "katel", "kotel", "qozon", "gaz qozon",
        "vaillant", "vailant", "valiant", "vaylant",
        "вайлант", "котел", "котёл", "қозон",
        "ariston", "buderus", "remexa", "airfel",
    ],
    "kir yuvish mashinasi": [
        "avtomat", "avtomat kir mashina",
        "kir mashina", "kir yuvish mashinasi",
        "kirmashina", "kirmoshina", "stiralka",
        "стиралка", "стиральная машина",
    ],
    "perforator": [
        "perforatorchi", "perfaratorchi",
        "perforator", "перфораторчи", "перфоратор",
    ],
    "santexnik": [
        "santexnik", "santexnika",
        "сантехник", "сантехника",
    ],
    "televizor": [
        "televizor", "televizor usta",
        "телевизор", "телевизор уста",
    ],
}

LOCATION_NAMES = [
    "Navoiy", "Charxiy", "Romanka", "Yangi bozor",
    "Salang", "Chodaklik", "Sud", "Vokzal",
    "Ximik", "Sorklet", "Kalve", "Baqachorsu",
    "Kosmonavt", "Qo'qon", "Kokand", "Коканд",
]

CATEGORY_WORDS = {
    "Aptekalar": [
        "apteka", "aptekalar", "dorixona", "dorixonalar",
        "аптека", "дорихона",
    ],
    "Choyxonalar": [
        "choyxona", "choyxonalar", "чайхана",
    ],
    "Gril": [
        "gril", "grill", "гриль",
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("kerakli_raqamlar")

db_pool = None

# O'zbekiston telefon raqamlari:
# +998901234567 yoki 901234567 ko'rinishlari.
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?998[\s().-]*)?"
    r"(?:\d[\s().-]*){9}(?!\d)"
)

STOP_WORDS = {
    "kerak", "raqam", "raqami", "telefon", "nomer",
    "ber", "bormi", "qayerda", "iltimos", "topib",
    "menga", "uchun", "kerakli", "raqamni",
}


# =====================================================
# MATNNI ME'YORLASHTIRISH
# =====================================================

def normalize(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()

    text = (
        text.replace("ё", "е")
        .replace("ў", "у")
        .replace("ғ", "г")
        .replace("қ", "к")
        .replace("ҳ", "х")
    )

    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def cyrillic_to_latin(text):
    """
    O'zbek kirill yozuvini qidiruv uchun lotinga o'tkazadi.
    """
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g",
        "д": "d", "е": "e", "ё": "yo", "ж": "j",
        "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "x", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sh",
        "ъ": "", "ы": "i", "ь": "", "э": "e",
        "ю": "yu", "я": "ya", "ў": "o",
        "қ": "q", "ғ": "g", "ҳ": "h",
    }

    result = []

    for char in (text or "").lower():
        result.append(mapping.get(char, char))

    return "".join(result)


def search_form(text):
    return normalize(cyrillic_to_latin(normalize(text)))


def get_phone_numbers(text):
    found = []

    for raw in PHONE_PATTERN.findall(text or ""):
        digits = re.sub(r"\D", "", raw)

        if len(digits) == 12 and digits.startswith("998"):
            phone = "+" + digits
        elif len(digits) == 9:
            phone = "+998" + digits
        else:
            continue

        if phone not in found:
            found.append(phone)

    return found


def detect_special_service(text):
    normalized = search_form(text)

    for service, aliases in SPECIAL_SERVICES.items():
        for alias in aliases:
            alias_normalized = search_form(alias)

            if re.search(
                r"(?<!\w)" + re.escape(alias_normalized) + r"(?!\w)",
                normalized,
            ):
                return service

    return None


def detect_category(text):
    normalized = search_form(text)

    for category, aliases in CATEGORY_WORDS.items():
        for alias in aliases:
            if search_form(alias) in normalized:
                return category

    return "Boshqa"


def detect_location(text):
    normalized = search_form(text)

    for location in LOCATION_NAMES:
        if search_form(location) in normalized:
            return location

    return ""


def extract_organization(text):
    """
    Telefon raqamlarini olib tashlab, xabardan nomni ajratadi.
    """
    cleaned = PHONE_PATTERN.sub(" ", text or "")

    result_lines = []

    for line in cleaned.splitlines():
        line = re.sub(r"[📂🏷📞☎️📍🟢🔹🔸]", " ", line)
        line = re.sub(
            r"(?i)\b(kategoriya|category|telefon|phone|raqam)\b",
            " ",
            line,
        )
        line = re.sub(r"\s+", " ", line).strip(" :-\t")

        if not line:
            continue

        if search_form(line) in {
            "aptekalar", "choyxonalar", "gril",
        }:
            continue

        result_lines.append(line)

    return " | ".join(result_lines)[:500]


# =====================================================
# BAZA: MA'LUMOTLARNI O'CHIRMASDAN MOSLASHTIRISH
# =====================================================

async def init_database():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            ".env faylida DATABASE_URL ko'rsatilmagan."
        )

    db_pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=1,
        max_size=5,
        timeout=60,
        command_timeout=60,
    )

    async with db_pool.acquire() as conn:
        # Jadval faqat mavjud bo'lmasa yaratiladi.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS krp_records (
                id BIGSERIAL PRIMARY KEY,
                organization TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Boshqa',
                location TEXT NOT NULL DEFAULT '',
                brand TEXT NOT NULL DEFAULT '',
                original_text TEXT NOT NULL DEFAULT '',
                source_chat TEXT NOT NULL DEFAULT '',
                source_message_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Faqat yetishmayotgan ustunlar qo'shiladi.
        # Hech qanday DROP TABLE yoki DELETE yo'q.
        migrations = [
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS organization
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS phone
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS category
            TEXT NOT NULL DEFAULT 'Boshqa'
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS location
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS brand
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS original_text
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS source_chat
            TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS source_message_id
            BIGINT
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS created_at
            TIMESTAMPTZ DEFAULT NOW()
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS updated_at
            TIMESTAMPTZ DEFAULT NOW()
            """,
            """
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS normalized_text
            TEXT NOT NULL DEFAULT ''
            """,
        ]

        for sql in migrations:
            await conn.execute(sql)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_phone_idx
            ON krp_records(phone)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_source_idx
            ON krp_records(source_chat, source_message_id)
        """)

    logger.info("Supabase/PostgreSQL bazasi tayyor.")


# =====================================================
# GURUH XABARLARINI SAQLASH
# =====================================================

async def is_group_admin(update, context):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return False

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False

    if user.is_bot:
        return False

    try:
        member = await context.bot.get_chat_member(
            chat.id,
            user.id,
        )

        return member.status in ("administrator", "creator")

    except Exception:
        logger.warning(
            "Admin holatini tekshirib bo'lmadi. "
            "Bot guruhda administrator ekanini tekshiring."
        )
        return False


async def save_group_message(update, context):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat or not message.text:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not await is_group_admin(update, context):
        return

    original_text = message.text.strip()

    if not original_text:
        return

    # Maxsus xizmat xabarlaridagi raqamlar umumiy bazaga kiritilmaydi.
    if detect_special_service(original_text):
        return

    phones = get_phone_numbers(original_text)

    if not phones:
        return

    organization = extract_organization(original_text)
    category = detect_category(original_text)
    location = detect_location(original_text)

    async with db_pool.acquire() as conn:
        for phone in phones:
            # Bir xil guruh xabari qayta kelganda dublikatni kamaytiradi.
            exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM krp_records
                    WHERE source_chat = $1
                      AND source_message_id = $2
                      AND phone = $3
                )
                """,
                str(chat.id),
                message.message_id,
                phone,
            )

            if exists:
                continue

            await conn.execute(
                """
                INSERT INTO krp_records (
                    organization,
                    phone,
                    category,
                    location,
                    brand,
                    original_text,
                    source_chat,
                    source_message_id,
                    normalized_text,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    NOW(), NOW()
                )
                """,
                organization,
                phone,
                category,
                location,
                "",
                original_text,
                str(chat.id),
                message.message_id,
                search_form(
                    organization + " " + original_text
                ),
            )

            logger.info(
                "Yangi raqam saqlandi: %s, guruh=%s",
                phone,
                chat.id,
            )


# =====================================================
# QIDIRUV
# =====================================================

def get_search_tokens(query):
    normalized = search_form(query)

    tokens = [
        token for token in normalized.split()
        if len(token) > 1 and token not in STOP_WORDS
    ]

    # Takrorlangan so'zlarni olib tashlash.
    return list(dict.fromkeys(tokens))


async def search_records(query):
    tokens = get_search_tokens(query)

    if not tokens:
        return []

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                organization,
                phone,
                category,
                location,
                brand,
                original_text,
                normalized_text
            FROM krp_records
            WHERE phone <> ''
            ORDER BY created_at DESC NULLS LAST
            LIMIT 10000
        """)

    matches = []

    for row in rows:
        combined = " ".join([
            row["organization"] or "",
            row["phone"] or "",
            row["category"] or "",
            row["location"] or "",
            row["brand"] or "",
            row["original_text"] or "",
            row["normalized_text"] or "",
        ])

        normalized_record = search_form(combined)

        # Har bir mazmunli so'z yozuvdan topilishi kerak.
        if all(token in normalized_record for token in tokens):
            matches.append(row)

    return matches[:10]


def format_results(rows):
    if not rows:
        return None

    output = []
    seen = set()

    for row in rows:
        phone = row["phone"] or ""
        organization = row["organization"] or "Nomi ko'rsatilmagan"
        location = row["location"] or ""
        category = row["category"] or ""

        key = (organization, phone, location)

        if key in seen:
            continue

        seen.add(key)

        item = f"🏷 {organization}\n📞 {phone}"

        if location:
            item += f"\n📍 {location}"

        if category and category != "Boshqa":
            item += f"\n📂 {category}"

        output.append(item)

    if not output:
        return None

    return "\n\n".join(output) + FOOTER


# =====================================================
# MAXSUS XIZMATLAR
# =====================================================

def format_special_service(service):
    return (
        f"🛠 Xizmat: {service.title()}\n\n"
        "📞 +998911517577\n"
        "📞 +998979600501"
        + FOOTER
    )


# =====================================================
# XABARLARNI QAYTA ISHLASH
# =====================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not message.text or not chat or not user:
        return

    if user.is_bot:
        return

    text = message.text.strip()

    # Maxsus xizmatlar har qanday chatda tekshiriladi.
    special = detect_special_service(text)

    if special:
        await message.reply_text(
            format_special_service(special),
            disable_web_page_preview=True,
        )

        # Bu xabar umumiy bazaga saqlanmaydi.
        return

    # Guruhda admin yuborgan raqamli xabarni saqlash.
    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await save_group_message(update, context)
        return

    # Shaxsiy chatdagi oddiy qidiruv.
    if chat.type == ChatType.PRIVATE:
        try:
            results = await search_records(text)
            answer = format_results(results)

            # Natija topilmasa, umuman javob bermaydi.
            if answer:
                await message.reply_text(
                    answer,
                    disable_web_page_preview=True,
                )

        except Exception:
            logger.exception("Qidiruv xatosi")


# =====================================================
# BOTNI ISHGA TUSHIRISH
# =====================================================

async def post_init(application):
    await init_database()


async def post_shutdown(application):
    global db_pool

    if db_pool:
        await db_pool.close()
        db_pool = None


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            ".env faylida BOT_TOKEN topilmadi."
        )

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60,
    )

    get_updates_request = HTTPXRequest(
        connection_pool_size=2,
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60,
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Kerakli Raqamlar PRO ishga tushmoqda...")

    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
