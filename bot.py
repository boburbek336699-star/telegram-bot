    phones = find_phones(text)

    if phones and is_advertisement(text):
        return

    # =====================================================
    # 3. KATEGORIYAGA MA'LUMOT SAQLASH
    # =====================================================

    category = detect_category(text)

    if phones and category:

        name = extract_name(
            text,
            phones[0]
        )

        for phone in phones:

            save_record(
                chat_id,
                category,
                name,
                phone,
                text
            )

        return

    # =====================================================
    # 4. ODDIY RAQAMLI XABAR
    # =====================================================

    if phones:

        name = extract_name(
            text,
            phones[0]
        )

        for phone in phones:

            save_record(
                chat_id,
                "Boshqa",
                name,
                phone,
                text
            )

        return

    # =====================================================
    # 5. KATEGORIYA SO'RASH
    # =====================================================

    query_normal = normalize(text)

    requested_category = None

    for category_name in CATEGORY_KEYWORDS:

        if normalize(category_name) in query_normal:

            requested_category = category_name
            break

    if requested_category:

        rows = search_category(
            chat_id,
            requested_category
        )

        if not rows:

            await update.message.reply_text(
                "🔎 Bu kategoriyada raqam topilmadi."
            )

            return

        answer = (
            f"📋 <b>{requested_category}</b>\n\n"
        )

        shown = set()

        for name, phone in rows:

            key = (
                name,
                phone
            )

            if key in shown:
                continue

            shown.add(key)

            answer += (
                f"🏷 <b>{name}</b>\n"
                f"📞 {phone}\n\n"
            )

        await update.message.reply_text(
            answer,
            parse_mode="HTML"
        )

        return

    # =====================================================
    # 6. NOM BO'YICHA QIDIRISH
    # =====================================================

    results = search_name(
        chat_id,
        text
    )

    if results:

        answer = "🔎 <b>Topilgan raqamlar:</b>\n\n"

        shown = set()

        for category, name, phone in results:

            if phone in shown:
                continue

            shown.add(phone)

            answer += (
                f"🏷 <b>{name}</b>\n"
                f"📞 <b>{phone}</b>\n\n"
            )

        await update.message.reply_text(
            answer,
            parse_mode="HTML"
        )

        return


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi"
        )

    init_db()

    Thread(
        target=run_web,
        daemon=True
    ).start()

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("🚀 PRO BOT ISHLADI!")

    application.run_polling()


if __name__ == "__main__":
    main()
