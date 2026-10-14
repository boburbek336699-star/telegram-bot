import os
import re
import logging
import unicodedata
import asyncio
from difflib import SequenceMatcher

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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

MY_NUMBERS = [
    "+998911517577",
    "+998979600501",
]

SHOPPING_BLOCK = """
━━━━━━━━━━━━━━
🛍 YASMINA SHOPPING 🛍
💖 Ayollar uchun ajoyib mahsulotlar!

👉 https://t.me/yasmina_shooooping
━━━━━━━━━━━━━━
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("kerakli-raqamlar-pro")

db_pool = None
save_lock = asyncio.Lock()


# =====================================================
# 1. TELEFON RAQAMLARINI ANIQLASH
# =====================================================

PHONE_RE = re.compile(
    r"(?<!\d)(?:"
    r"\+?998[\s().\-]*\d{2}"
    r"[\s().\-]*\d{3}"
    r"[\s().\-]*\d{2}"
    r"[\s().\-]*\d{2}"
    r"|"
    r"0\d{2}[\s().\-]*\d{3}"
    r"[\s().\-]*\d{2}"
    r"[\s().\-]*\d{2}"
    r")(?!\d)"
)


def normalize(text):
    text = unicodedata.normalize(
        "NFKC",
        text or "",
    ).lower()

    text = (
        text.replace("ў", "у")
        .replace("қ", "к")
        .replace("ғ", "г")
        .replace("ҳ", "х")
        .replace("ё", "е")
    )

    text = re.sub(r"[’'`ʻʼ]", "", text)

    text = re.sub(
        r"[^0-9a-zа-яәөүқғҳхіїє\s+]",
        " ",
        text,
    )

    return re.sub(r"\s+", " ", text).strip()


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw)

    if digits.startswith("998") and len(digits) == 12:
        return "+" + digits

    if digits.startswith("0") and len(digits) == 9:
        return "+998" + digits[1:]

    if len(digits) == 9:
        return "+998" + digits

    return ""


# =====================================================
# 2. MAXSUS XIZMATLAR
# =====================================================

SPECIALS = {
    "konditsioner": {
        "words": [
            "konditsioner",
            "konditsaner",
            "kanditsaner",
            "konditsioner ustasi",
            "konditsioner tuzatish",
            "konditsioner tozalash",
            "freon quyish",
            "konditsioner remont",
            "кондиционер",
            "мастер кондиционеров",
            "ремонт кондиционера",
            "чистка кондиционера",
            "заправка фреоном",
        ],
        "title": "❄️ KONDITSIONER XIZMATI",
    },

    "katyol": {
        "words": [
            "katyol",
            "kotel",
            "qozon",
            "gaz qozoni",
            "gaz katyol",
            "katyol ustasi",
            "katyol tuzatish",
            "katyol remont",
            "vaillant",
            "vailant",
            "vaylant",
            "вайлант",
            "котел",
            "котёл",
            "газовый котел",
            "газовый котел мастер",
            "ремонт котла",
        ],
        "title": "🔥 KATYOL VA GAZ QOZONI XIZMATI",
    },

    "kir_mashina": {
        "words": [
            "kirmoshina",
            "kir moshina",
            "kir mashina",
            "kir yuvish mashinasi",
            "avtomat kir yuvish mashinasi",
            "kir mashina ustasi",
            "kir mashina tuzatish",
            "стиральная машина",
            "стиралка",
            "ремонт стиральной машины",
            "мастер по стиральным машинам",
        ],
        "title": "🧺 KIR YUVISH MASHINASI TA'MIRLASH",
    },

    "perforator": {
        "words": [
            "perforator",
            "perfarator",
            "beton teshish",
            "beton teshadigan usta",
            "perforator ustasi",
            "перфоратор",
            "бурение бетона",
        ],
        "title": "🛠 PERFORATOR XIZMATI",
    },

    "santexnik": {
        "words": [
            "santexnik",
            "santexnika",
            "santehnik",
            "suv ustasi",
            "kran tuzatish",
            "truba tuzatish",
            "vodoprovod ustasi",
            "сантехник",
            "сантехника",
            "ремонт крана",
            "ремонт труб",
        ],
        "title": "🚰 SANTEXNIK XIZMATI",
    },

    "televizor": {
        "words": [
            "televizor",
            "televizor ustasi",
            "televizor tuzatish",
            "televizor tamirlash",
            "tv ustasi",
            "телевизор",
            "ремонт телевизора",
            "мастер по телевизорам",
        ],
        "title": "📺 TELEVIZOR TA'MIRLASH",
    },
}


def contains_phrase(text, phrase):
    """
    Butun so'z yoki ibora mosligini tekshiradi.
    Masalan, 'tv' kabi qisqa iboralarni tasodifan
    boshqa so'z ichidan topib olmaslikka yordam beradi.
    """

    q = normalize(text)
    p = normalize(phrase)

    if not p:
        return False

    return bool(
        re.search(
            r"(?<!\w)" + re.escape(p) + r"(?!\w)",
            q,
        )
    )


def find_special(text):
    for key, item in SPECIALS.items():
        for word in item["words"]:
            if contains_phrase(text, word):
                return key, item

    return None, None


# =====================================================
# 3. HUDUDLARNI ANIQLASH
# =====================================================

LOCATION_ALIASES = {
    "Qo'qon": [
        "qoqon",
        "kokand",
        "qo'qon",
        "кукан",
        "коканд",
    ],

    "Navoiy": [
        "navoiy",
        "навоий",
    ],

    "Charxiy": [
        "charxiy",
        "charxiy 8 dom",
        "чархия",
    ],

    "G'ishko'prik": [
        "gishkuprik",
        "gish kuprik",
        "gishkoprik",
        "гишкуприк",
    ],

    "Romanka": [
        "romanka",
    ],

    "Yangi bozor": [
        "yangi bozor",
        "янги бозор",
    ],

    "Salen": [
        "salen",
        "salang",
    ],

    "Chodaklik": [
        "chodaklik",
    ],

    "Vokzal": [
        "vokzal",
        "вокзал",
    ],

    "Ximik": [
        "ximik",
        "химик",
    ],

    "Kalve": [
        "kalve",
    ],

    "Baqachorsu": [
        "baqachorsu",
    ],

    "Kosmonavt": [
        "kosmonavt",
        "космонавт",
    ],

    "Sud": [
        "sud",
    ],
}


def find_location(text):
    found = []

    for canonical, aliases in LOCATION_ALIASES.items():
        for alias in aliases:
            if contains_phrase(text, alias):
                found.append(
                    (len(normalize(alias)), canonical)
                )

    if not found:
        return ""

    found.sort(reverse=True)

    return found[0][1]


# =====================================================
# 4. XIZMAT TURINI ANIQLASH
# =====================================================

CATEGORY_ALIASES = {
    "Apteka": [
        "apteka",
        "dorixona",
        "аптека",
    ],

    "Ko'z klinikasi": [
        "koz doktori",
        "koz shifokori",
        "ko'z doktori",
        "ko'z shifokori",
        "glaznoy",
        "oftalmolog",
        "офтальмолог",
        "глазной врач",
    ],

    "Klinika / shifokor": [
        "klinika",
        "shifokor",
        "doktor",
        "vrach",
        "клиника",
        "врач",
    ],

    "Tish shifokori": [
        "tish doktori",
        "tish shifokori",
        "stomatolog",
        "стоматолог",
    ],

    "Bolalar shifokori": [
        "bolalar doktori",
        "bolalar shifokori",
        "pediatr",
        "педиатр",
    ],

    "Oziq-ovqat": [
        "oziq ovqat",
        "magazin",
        "do'kon",
        "магазин",
    ],
}


def classify(text):
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            if contains_phrase(text, alias):
                return category

    q = normalize(text)

    if any(
        word in q
        for word in [
            "usta",
            "tamirlash",
            "ta mirlash",
            "remont",
            "ремонт",
        ]
    ):
        return "Usta"

    return "Boshqa"


def query_category(text):
    return classify(text)


# =====================================================
# 5. NOMNI ANIQLASH
# =====================================================

NON_NAME_WORDS = {
    "telefon",
    "telefoni",
    "raqam",
    "raqami",
    "nomer",
    "numeri",
    "ber",
    "bering",
    "kerak",
    "bormi",
    "iltimos",
    "nomerini",
    "raqamini",
}


def clean_candidate(value):
    value = PHONE_RE.sub("", value)

    value = re.sub(
        r"^[\s:;,.—–\-•📞☎️]+",
        "",
        value,
    )

    value = re.sub(
        r"[\s:;,.—–\-•📞☎️]+$",
        "",
        value,
    )

    return value.strip()


def valid_name(value):
    if not value:
        return False

    q = normalize(value)

    if len(q) < 3:
        return False

    words = q.split()

    if not words:
        return False

    if all(word in NON_NAME_WORDS for word in words):
        return False

    if PHONE_RE.search(value):
        return False

    return True


def extract_name(text, phone_match):
    """
    Telefon joylashgan satrdan nomni topishga urinadi.
    Nom ishonchli aniqlanmasa, bo'sh qaytaradi.
    """

    lines = text.splitlines()
    offset = 0

    for index, line in enumerate(lines):
        line_end = offset + len(line)

        if offset <= phone_match.start() <= line_end:
            candidate = clean_candidate(line)

            candidate_normalized = normalize(candidate)

            # "Telefon:" kabi xizmatga oid bo'lmagan
            # so'zlarni korxona nomi deb qabul qilmaymiz.
            if valid_name(candidate):
                return candidate[:180]

            # Raqam alohida qatorda bo'lsa,
            # avval uning oldidagi nomni tekshiramiz.
            if index > 0:
                previous = clean_candidate(
                    lines[index - 1]
                )

                if valid_name(previous):
                    return previous[:180]

            if index + 1 < len(lines):
                following = clean_candidate(
                    lines[index + 1]
                )

                if valid_name(following):
                    return following[:180]

            return ""

        offset = line_end + 1

    return ""


# =====================================================
# 6. MA'LUMOTLAR BAZASINI TAYYORLASH
# =====================================================

async def init_database():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL .env faylida topilmadi."
        )

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
        ssl="require",
    )

    async with db_pool.acquire() as conn:
        # Asosiy jadval.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS krp_records (
                id BIGSERIAL PRIMARY KEY,
                organization TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL,
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

        # Eski bazadagi ustunlar yetishmasa,
        # qo'shamiz. Mavjud ma'lumotlar o'chmaydi.
        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS organization
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS phone
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS category
            TEXT NOT NULL DEFAULT 'Boshqa'
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS location
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS brand
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS original_text
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS source_chat
            TEXT NOT NULL DEFAULT ''
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS source_message_id
            BIGINT
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS created_at
            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """)

        await conn.execute("""
            ALTER TABLE krp_records
            ADD COLUMN IF NOT EXISTS updated_at
            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        """)

        # Raqam va manba xabarlarini bog'lash.
        # Bitta raqam boshqa guruhda uchrasa,
        # uning manbasi ham saqlanishi mumkin.
        await conn.execute("""
    CREATE TABLE IF NOT EXISTS krp_sources (
        id BIGSERIAL PRIMARY KEY,
        record_id BIGINT NOT NULL,
        source_chat TEXT NOT NULL,
        source_message_id BIGINT NOT NULL,
        source_chat_title TEXT NOT NULL DEFAULT '',
        original_text TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (
            record_id,
            source_chat,
            source_message_id
        )
    )
""")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_phone_idx
            ON krp_records(phone)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_location_idx
            ON krp_records(location)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_category_idx
            ON krp_records(category)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_updated_idx
            ON krp_records(updated_at DESC)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS krp_sources_chat_idx
            ON krp_sources(source_chat, source_message_id)
        """)

    log.info("PostgreSQL/Supabase bazasiga ulanish muvaffaqiyatli.")


# =====================================================
# 7. RAQAMLARNI SAQLASH
# =====================================================

async def save_source_message(
    text,
    chat_id,
    message_id,
    chat_title="",
):
    matches = list(PHONE_RE.finditer(text))

    if not matches:
        return

    # Maxsus xizmat xabaridagi boshqa ustalarning
    # raqamlarini oddiy baza yozuvi sifatida saqlamaymiz.
    special_key, _ = find_special(text)

    if special_key:
        log.info(
            "Maxsus xizmat xabari: oddiy baza saqlashi o'tkazildi."
        )
        return

    location = find_location(text)
    category = classify(text)

    async with save_lock:
        for match in matches:
            phone = normalize_phone(match.group())

            if not phone:
                continue

            organization = extract_name(text, match)

            # Nom topilmagan yozuvni taxmin bilan
            # to'ldirmaymiz. Raqamni ham saqlash
            # mumkin, lekin qidiruvda nom talab qilinadi.
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    # Bir xil raqam uchun parallel yozuvlar
                    # yaratilish ehtimolini kamaytiradi.
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1))",
                        phone,
                    )

                    existing = await conn.fetchrow("""
                        SELECT id, organization, category,
                               location, original_text
                        FROM krp_records
                        WHERE phone = $1
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """, phone)

                    if existing:
                        record_id = existing["id"]

                        # Yaxshiroq ma'lumot bo'lsa,
                        # bo'sh maydonlarni to'ldiramiz.
                        new_org = (
                            existing["organization"]
                            or organization
                        )

                        new_category = (
                            existing["category"]
                            if existing["category"] != "Boshqa"
                            else category
                        )

                        new_location = (
                            existing["location"]
                            or location
                        )

                        new_text = (
                            text[:12000]
                            if len(text) > len(
                                existing["original_text"] or ""
                            )
                            else existing["original_text"]
                        )

                        await conn.execute("""
                            UPDATE krp_records
                            SET organization = $1,
                                category = $2,
                                location = $3,
                                original_text = $4,
                                updated_at = NOW()
                            WHERE id = $5
                        """,
                            new_org,
                            new_category,
                            new_location,
                            new_text,
                            record_id,
                        )

                    else:
                        record_id = await conn.fetchval("""
                            INSERT INTO krp_records (
                                organization,
                                phone,
                                category,
                                location,
                                original_text,
                                source_chat,
                                source_message_id
                            )
                            VALUES ($1,$2,$3,$4,$5,$6,$7)
                            RETURNING id
                        """,
                            organization,
                            phone,
                            category,
                            location,
                            text[:12000],
                            str(chat_id),
                            message_id,
                        )

                    # Manba xabarini ham saqlaymiz.
                    await conn.execute("""
                        INSERT INTO krp_sources (
                            record_id,
                            source_chat,
                            source_message_id,
                            source_chat_title,
                            original_text
                        )
                        VALUES ($1,$2,$3,$4,$5)
                        ON CONFLICT (
                            record_id,
                            source_chat,
                            source_message_id
                        )
                        DO NOTHING
                    """,
                        record_id,
                        str(chat_id),
                        message_id,
                        chat_title[:250],
                        text[:12000],
                    )

    log.info(
        "Xabar saqlandi: chat=%s message=%s raqamlar=%s",
        chat_id,
        message_id,
        len(matches),
    )


# =====================================================
# 8. QIDIRUV SO'ROVINI TAYYORLASH
# =====================================================

STOP_WORDS = {
    "raqami",
    "raqam",
    "nomer",
    "numeri",
    "telefon",
    "telefoni",
    "ber",
    "bering",
    "kerak",
    "bormi",
    "iltimos",
    "menga",
    "telefonini",
    "raqamini",
    "nomerini",
    "topib",
    "bervorilar",
    "tashavor",
    "qayerda",
    "qayerdan",
    "kimda",
    "bor",
    "bor-mi",
    "uchun",
    "менга",
    "номер",
    "телефон",
    "нужен",
    "нужна",
    "дайте",
    "пожалуйста",
}


def query_words(query):
    words = normalize(query).split()

    return [
        word
        for word in words
        if word not in STOP_WORDS and len(word) > 1
    ]


def has_search_intent(text):
    q = normalize(text)

    intent_words = [
        "raqami",
        "raqam",
        "nomer",
        "numeri",
        "telefon",
        "kerak",
        "bormi",
        "bering",
        "topib ber",
        "telefonini",
        "raqamini",
        "nomerini",
        "номер",
        "телефон",
        "дайте",
        "нужен",
        "нужна",
        "ищу",
    ]

    return any(
        contains_phrase(q, word)
        for word in intent_words
    )


# =====================================================
# 9. TEZKOR VA ANIQLIKKA YO'NALTIRILGAN QIDIRUV
# =====================================================

async def search_records(query):
    words = query_words(query)

    if not words:
        return []

    requested_location = find_location(query)
    requested_category = query_category(query)

    async with db_pool.acquire() as conn:
        # Faqat so'rov so'zlariga mos yozuvlarni
        # bazadan olishga harakat qilamiz.
        conditions = []
        params = []

        searchable_columns = [
            "organization",
            "phone",
            "category",
            "location",
            "brand",
            "original_text",
        ]

        for word in words:
            pattern = "%" + word + "%"

            column_conditions = []

            for column in searchable_columns:
                params.append(pattern)

                column_conditions.append(
                    f"{column} ILIKE ${len(params)}"
                )

            conditions.append(
                "(" + " OR ".join(column_conditions) + ")"
            )

        where_sql = " OR ".join(conditions)

        sql = f"""
            SELECT id, organization, phone, category,
                   location, brand, original_text,
                   updated_at
            FROM krp_records
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT 3000
        """

        rows = await conn.fetch(sql, *params)

    results = []

    q_normalized = normalize(query)

    for row in rows:
        name = row["organization"] or ""
        phone = row["phone"] or ""
        category = row["category"] or "Boshqa"
        location = row["location"] or ""
        original_text = row["original_text"] or ""

        # Nom aniq bo'lmasa, natijani chiqarib yubormaymiz.
        if not valid_name(name):
            continue

        # Telefon raqamini format bo'yicha tekshiramiz.
        if not normalize_phone(phone):
            continue

        # So'rovda joy ko'rsatilgan bo'lsa,
        # yozuvda ham aynan shu joy bo'lishi shart.
        if requested_location:
            if (
                normalize(requested_location)
                not in normalize(location)
            ):
                continue

        # Muayyan xizmat so'ralganda, boshqa toifadagi
        # yozuvlarni chiqarib yubormaslikka harakat qilamiz.
        if requested_category != "Boshqa":
            if category != requested_category:
                combined = normalize(
                    name + " " + original_text
                )

                category_aliases = CATEGORY_ALIASES.get(
                    requested_category,
                    [],
                )

                if not any(
                    contains_phrase(combined, alias)
                    for alias in category_aliases
                ):
                    continue

        searchable_text = normalize(" ".join([
            name,
            phone,
            category,
            location,
            row["brand"] or "",
            original_text,
        ]))

        hits = sum(
            1
            for word in words
            if word in searchable_text
        )

        if not hits:
            continue

        # Hudud yoki aniq xizmat ko'rsatilgan bo'lsa,
        # tegishli moslikni qo'shimcha tekshiramiz.
        if requested_location:
            if normalize(requested_location) not in normalize(
                location
            ):
                continue

        # Bitta so'zli so'rovga kamida bitta,
        # uzunroq so'rovga kamida ikkita mos so'z kerak.
        minimum_hits = 1 if len(words) == 1 else 2

        if hits < minimum_hits:
            continue

        # Ism va so'rov o'rtasidagi o'xshashlik.
        name_similarity = SequenceMatcher(
            None,
            q_normalized,
            normalize(name),
        ).ratio()

        score = hits + name_similarity

        results.append((score, row))

    results.sort(
        key=lambda item: (
            -item[0],
            item[1]["organization"].lower(),
        )
    )

    # Telefon raqami bo'yicha natijalarni takrorlamaymiz.
    final_rows = []
    seen_phones = set()

    for _, row in results:
        phone = row["phone"]

        if phone in seen_phones:
            continue

        seen_phones.add(phone)
        final_rows.append(row)

        if len(final_rows) >= 10:
            break

    return final_rows


# =====================================================
# 10. JAVOBNI TAYYORLASH
# =====================================================

def format_results(rows):
    if not rows:
        return ""

    lines = ["🔎 TOPILGAN NATIJALAR"]

    for row in rows:
        name = row["organization"]
        phone = row["phone"]
        location = row["location"] or ""
        category = row["category"] or ""

        if not valid_name(name):
            continue

        place_line = (
            f"\n📍 Hudud: {location}"
            if location else ""
        )

        category_line = (
            f"\n🏷 Xizmat: {category}"
            if category and category != "Boshqa"
            else ""
        )

        lines.append(
            f"\n📌 {name}"
            f"{place_line}"
            f"{category_line}"
            f"\n📞 {phone}"
        )

    if len(lines) == 1:
        return ""

    return "\n".join(lines)


async def send_reply(update, text):
    if not update.effective_message or not text:
        return

    full_text = text + "\n\n" + SHOPPING_BLOCK

    while len(full_text) > 3900:
        cut = full_text.rfind("\n", 0, 3900)

        if cut < 1000:
            cut = 3900

        await update.effective_message.reply_text(
            full_text[:cut],
            disable_web_page_preview=True,
        )

        full_text = full_text[cut:].lstrip()

    await update.effective_message.reply_text(
        full_text,
        disable_web_page_preview=True,
    )


# =====================================================
# 11. ASOSIY XABAR HANDLERI
# =====================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    text = message.text or message.caption or ""

    if not text:
        return

    # Botning o'z xabarlariga javob bermaydi.
    if message.from_user and message.from_user.is_bot:
        return

    is_group = chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    )

    # 1. Maxsus xizmatlar.
    # Tanlangan 1-variant bo'yicha xizmat so'zi
    # xabarda uchrasa, bot raqamlarni chiqaradi.
    special_key, special = find_special(text)

    if special:
        # Bunday xabardagi boshqa ustalarning
        # raqamlarini oddiy bazaga saqlamaymiz.
        if is_group:
            log.info(
                "Maxsus xizmat xabari oddiy bazaga saqlanmadi."
            )

        answer = (
            special["title"]
            + "\n\n"
            + "\n".join(
                f"📞 {number}"
                for number in MY_NUMBERS
            )
            + "\n\n"
            + "✅ Tez • Sifatli • Ishonchli"
        )

        await send_reply(update, answer)
        return

    # 2. Oddiy guruh xabarlaridagi raqamlarni saqlash.
    if is_group and PHONE_RE.search(text):
        try:
            await save_source_message(
                text=text,
                chat_id=chat.id,
                message_id=message.message_id,
                chat_title=chat.title or "",
            )

        except Exception:
            log.exception(
                "Guruh xabarini saqlashda xato"
            )

    # 3. Shaxsiy chatda foydalanuvchi yozgan matn
    # qidiruv so'rovi sifatida ko'rib chiqiladi.
    # Guruhda esa oddiy suhbatga keraksiz javob bermaslik
    # uchun qidiruv niyati bo'lishi kerak.
    if is_group and not has_search_intent(text):
        return

    try:
        rows = await search_records(text)

        if not rows:
            # Foydalanuvchi talabiga ko'ra:
            # natija topilmasa, umuman javob yo'q.
            return

        answer = format_results(rows)

        if answer:
            await send_reply(update, answer)

    except Exception:
        # Xato bo'lsa ham foydalanuvchiga uydirma
        # natija yoki keraksiz xabar yubormaymiz.
        log.exception("Qidiruvda xato")


# =====================================================
# 12. ISHGA TUSHIRISH
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
            "BOT_TOKEN .env faylida topilmadi."
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL .env faylida topilmadi."
        )

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

    log.info("KERAKLI RAQAMLAR PRO ishga tushmoqda.")

    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
