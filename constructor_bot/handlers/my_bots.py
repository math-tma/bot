from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

import database
from database import pool
from keyboards.bot_create_menu import my_bots_kb, bot_detail_kb
from keyboards.main_menu import back_to_main_kb, template_select_kb, confirm_kb
from utils.billing import can_create_bot

router = Router()

TEMPLATE_NAMES = {
    "quiz": "🎯 Quiz bot",
    "shop": "🛒 Do'kon bot",
    "broadcaster": "📢 Avto xabar bot",
    "referral": "👥 Referral bot",
    "kinobot": "🎬 Kino bot",
}


# ═══════════════════════════════════════
# MENING BOTLARIM
# ═══════════════════════════════════════

@router.callback_query(F.data == "my_bots")
async def my_bots_handler(callback: CallbackQuery):
    async with database.pool.acquire() as conn:
        bots = await conn.fetch("""
            SELECT id, bot_username, template_type, is_running, created_at
            FROM bots WHERE user_id = $1
            ORDER BY created_at DESC
        """, callback.from_user.id)

    if not bots:
        await callback.message.edit_text(
            "🤖 <b>Mening botlarim</b>\n\n"
            "Hali birorta bot yaratmadingiz.\n"
            "Yangi bot yaratish uchun «Bot yaratish» tugmasini bosing.",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    bots_list = [dict(b) for b in bots]
    running = sum(1 for b in bots_list if b['is_running'])

    await callback.message.edit_text(
        f"🤖 <b>Mening botlarim</b>\n\n"
        f"Jami: <b>{len(bots_list)} ta</b> | "
        f"Faol: <b>{running} ta</b>\n\n"
        f"Botni tanlang:",
        reply_markup=my_bots_kb(bots_list),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# BOT DETAIL
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("bot_detail_"))
async def bot_detail_handler(callback: CallbackQuery):
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        bot = await conn.fetchrow("""
            SELECT * FROM bots WHERE id = $1 AND user_id = $2
        """, bot_id, callback.from_user.id)

    if not bot:
        await callback.answer("❌ Bot topilmadi!", show_alert=True)
        return

    bot = dict(bot)
    status = "✅ Ishlayapti" if bot['is_running'] else "❌ To'xtatilgan"
    template_name = TEMPLATE_NAMES.get(bot['template_type'], "Noma'lum")
    created = bot['created_at'].strftime('%d.%m.%Y')

    text = (
        f"🤖 <b>@{bot['bot_username'] or 'noma\'lum'}</b>\n\n"
        f"📦 Tur: {template_name}\n"
        f"📊 Holat: {status}\n"
        f"📅 Yaratilgan: {created}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=bot_detail_kb(bot_id, bot['is_running']),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# BOT ISHGA TUSHIRISH / TO'XTATISH
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("bot_start_"))
async def bot_start_handler(callback: CallbackQuery, bot: Bot):
    bot_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    can, reason = await can_create_bot(user_id)
    if not can:
        await callback.answer(f"❌ {reason}", show_alert=True)
        return

    async with database.pool.acquire() as conn:
        bot_data = await conn.fetchrow("""
            SELECT * FROM bots WHERE id = $1 AND user_id = $2
        """, bot_id, user_id)

        if not bot_data:
            await callback.answer("❌ Bot topilmadi!", show_alert=True)
            return

        await conn.execute("""
            UPDATE bots SET is_running = TRUE WHERE id = $1
        """, bot_id)

    # Webhook boshqaruvchisidan ishga tushirish
    from webhook.bot_manager import start_template_bot
    await start_template_bot(dict(bot_data))

    await callback.answer("✅ Bot ishga tushirildi!", show_alert=True)
    await bot_detail_handler(callback)


@router.callback_query(F.data.startswith("bot_stop_"))
async def bot_stop_handler(callback: CallbackQuery):
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE bots SET is_running = FALSE WHERE id = $1 AND user_id = $2
        """, bot_id, callback.from_user.id)

    from webhook.bot_manager import stop_template_bot
    await stop_template_bot(bot_id)

    await callback.answer("⏹ Bot to'xtatildi!", show_alert=True)
    await bot_detail_handler(callback)


# ═══════════════════════════════════════
# BOT O'CHIRISH
# ═══════════════════════════════════════

@router.callback_query(
    F.data.startswith("bot_delete_") & ~F.data.startswith("bot_delete_confirm_")
)
async def bot_delete_confirm_handler(callback: CallbackQuery):
    bot_id = int(callback.data.split("_")[-1])
    await callback.message.edit_text(
        "🗑️ <b>Botni o'chirish</b>\n\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi!\n"
        "Botni o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_kb(
            confirm_data=f"bot_delete_confirm_{bot_id}",
            cancel_data=f"bot_detail_{bot_id}"
        ),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bot_delete_confirm_"))
async def bot_delete_handler(callback: CallbackQuery):
    bot_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    async with database.pool.acquire() as conn:
        bot_data = await conn.fetchrow("""
            SELECT * FROM bots WHERE id = $1 AND user_id = $2
        """, bot_id, user_id)

        if not bot_data:
            await callback.answer("❌ Bot topilmadi!", show_alert=True)
            return

        # Webhookni o'chirish
        from webhook.bot_manager import stop_template_bot
        await stop_template_bot(bot_id)

        # DBdan o'chirish
        await conn.execute("DELETE FROM bots WHERE id = $1", bot_id)

    await callback.answer("🗑️ Bot o'chirildi!", show_alert=True)
    await my_bots_handler(callback)


# ═══════════════════════════════════════
# BOT YARATISH — SHABLON TANLASH
# ═══════════════════════════════════════

@router.callback_query(F.data == "create_bot")
async def create_bot_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    can, reason = await can_create_bot(user_id)

    if not can:
        await callback.message.edit_text(
            f"❌ <b>Bot yaratib bo'lmaydi</b>\n\n{reason}",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🆕 <b>Bot yaratish</b>\n\n"
        "Qaysi turdagi bot yaratmoqchisiz?",
        reply_markup=template_select_kb(),
        parse_mode="HTML"
    )
    await callback.answer()
