from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

import database
from database import pool
from database import get_setting, set_setting
from keyboards.admin_menu import (
    admin_main_kb, admin_users_kb, admin_user_action_kb,
    admin_payments_kb, admin_payment_action_kb, admin_bots_kb,
    admin_bot_action_kb, admin_broadcast_kb, admin_settings_kb,
    admin_channels_kb, admin_back_kb
)
from keyboards.main_menu import back_to_main_kb
from utils.billing import add_balance, reactivate_bots_if_balance
from utils.notifications import broadcast_message, notify_payment_confirmed, notify_payment_rejected
from config import ADMIN_ID

router = Router()


class AdminStates(StatesGroup):
    # Sozlamalar
    waiting_daily_price = State()
    waiting_trial_days = State()
    waiting_referral_bonus = State()
    waiting_payment_card = State()
    # Kanal
    waiting_channel_id = State()
    waiting_channel_name = State()
    waiting_channel_url = State()
    # Xabar yuborish
    waiting_broadcast_text = State()
    # Balans qo'shish
    waiting_add_balance_amount = State()
    # Foydalanuvchi qidirish
    waiting_search_user = State()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ═══════════════════════════════════════
# ADMIN PANEL ASOSIY
# ═══════════════════════════════════════

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_main")
async def admin_main_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# STATISTIKA
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    async with database.pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        trial_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE trial_ends_at > NOW()"
        )
        banned_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_banned = TRUE"
        )
        total_bots = await conn.fetchval("SELECT COUNT(*) FROM bots")
        running_bots = await conn.fetchval(
            "SELECT COUNT(*) FROM bots WHERE is_running = TRUE"
        )
        today_income = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0) FROM daily_charges
            WHERE DATE(charged_at) = CURRENT_DATE
        """)
        month_income = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0) FROM daily_charges
            WHERE DATE_TRUNC('month', charged_at) = DATE_TRUNC('month', NOW())
        """)
        pending_payments = await conn.fetchval(
            "SELECT COUNT(*) FROM payments WHERE status = 'pending'"
        )

    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total_users}</b>\n"
        f"🎁 Trialdagilar: <b>{trial_users}</b>\n"
        f"🚫 Banlangan: <b>{banned_users}</b>\n\n"
        f"🤖 Jami botlar: <b>{total_bots}</b>\n"
        f"✅ Ishlayotganlar: <b>{running_bots}</b>\n\n"
        f"💰 Bugungi daromad: <b>{today_income:,} so'm</b>\n"
        f"📅 Oylik daromad: <b>{month_income:,} so'm</b>\n\n"
        f"⏳ Kutayotgan to'lovlar: <b>{pending_payments}</b>"
    )

    await callback.message.edit_text(
        text, reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# FOYDALANUVCHILAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_users")
async def admin_users_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "👥 <b>Foydalanuvchilar</b>",
        reply_markup=admin_users_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users_list")
async def admin_users_list_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    async with database.pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT user_id, username, full_name, balance, is_banned, created_at
            FROM users ORDER BY created_at DESC LIMIT 20
        """)

    if not users:
        await callback.answer("Bo'sh", show_alert=True)
        return

    lines = []
    for u in users:
        ban = "🚫" if u['is_banned'] else "✅"
        lines.append(
            f"{ban} <b>{u['full_name']}</b> | "
            f"<code>{u['user_id']}</code> | "
            f"{u['balance']:,} so'm"
        )

    await callback.message.edit_text(
        f"👥 <b>Foydalanuvchilar (oxirgi 20):</b>\n\n" + "\n".join(lines),
        reply_markup=admin_users_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users_search")
async def admin_users_search_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_search_user)
    await callback.message.edit_text(
        "🔍 Foydalanuvchi ID yoki username kiriting:"
    )
    await callback.answer()


@router.message(AdminStates.waiting_search_user)
async def admin_search_user_result(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    query = message.text.strip().replace("@", "")

    async with database.pool.acquire() as conn:
        try:
            user_id = int(query)
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
        except ValueError:
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE username = $1", query
            )

    await state.clear()

    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return

    await send_user_info(message, dict(user))


async def send_user_info(target, user: dict):
    """Foydalanuvchi ma'lumotlarini ko'rsatish"""
    status = "🚫 Banlangan" if user['is_banned'] else "✅ Faol"
    trial = user['trial_ends_at']
    trial_text = (
        f"🎁 Trial: {trial.strftime('%d.%m.%Y')}" if trial and trial > datetime.now()
        else "—"
    )

    text = (
        f"👤 <b>{user['full_name']}</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"📱 Username: @{user['username'] or 'yo\'q'}\n"
        f"💰 Balans: <b>{user['balance']:,} so'm</b>\n"
        f"📊 Holat: {status}\n"
        f"{trial_text}\n"
        f"📅 Ro'yxat: {user['created_at'].strftime('%d.%m.%Y')}"
    )

    kb = admin_user_action_kb(user['user_id'], user['is_banned'])

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_ban_"))
async def admin_ban_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned = TRUE WHERE user_id = $1", user_id
        )
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await callback.answer("🚫 Foydalanuvchi banlandi!", show_alert=True)
    await send_user_info(callback, dict(user))


@router.callback_query(F.data.startswith("admin_unban_"))
async def admin_unban_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned = FALSE WHERE user_id = $1", user_id
        )
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await callback.answer("✅ Ban olib tashlandi!", show_alert=True)
    await send_user_info(callback, dict(user))


@router.callback_query(F.data.startswith("admin_add_balance_"))
async def admin_add_balance_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    await state.set_state(AdminStates.waiting_add_balance_amount)
    await state.update_data(target_user_id=user_id)
    await callback.message.edit_text(
        f"💰 Foydalanuvchi <code>{user_id}</code> ga qancha so'm qo'shish kerak?",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_add_balance_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text.replace(" ", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return

    data = await state.get_data()
    user_id = data['target_user_id']
    await state.clear()

    await add_balance(user_id, amount)
    reactivated = await reactivate_bots_if_balance(user_id)

    await message.answer(
        f"✅ {user_id} ga <b>{amount:,} so'm</b> qo'shildi.\n"
        f"Qayta ishga tushgan botlar: {len(reactivated)} ta",
        parse_mode="HTML"
    )

    await notify_payment_confirmed(bot, user_id, amount)


# ═══════════════════════════════════════
# TO'LOVLAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_payments")
async def admin_payments_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "💳 <b>To'lovlar</b>",
        reply_markup=admin_payments_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_payments_pending")
async def admin_payments_pending_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    async with database.pool.acquire() as conn:
        payments = await conn.fetch("""
            SELECT p.id, p.user_id, p.amount, p.created_at,
                   u.full_name, u.username
            FROM payments p JOIN users u ON p.user_id = u.user_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at ASC
        """)

    if not payments:
        await callback.answer("✅ Kutayotgan to'lovlar yo'q!", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for p in payments:
        buttons.append([InlineKeyboardButton(
            text=f"#{p['id']} | {p['full_name']} | {p['amount']:,} so'm",
            callback_data=f"admin_view_payment_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_payments")])

    await callback.message.edit_text(
        f"⏳ <b>Kutayotgan to'lovlar: {len(payments)} ta</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_view_payment_"))
async def admin_view_payment_handler(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    payment_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        payment = await conn.fetchrow("""
            SELECT p.*, u.full_name, u.username
            FROM payments p JOIN users u ON p.user_id = u.user_id
            WHERE p.id = $1
        """, payment_id)

    if not payment:
        await callback.answer("❌ Topilmadi!", show_alert=True)
        return

    await bot.send_photo(
        callback.from_user.id,
        photo=payment['check_file_id'],
        caption=(
            f"💳 <b>To'lov #{payment['id']}</b>\n\n"
            f"👤 {payment['full_name']}\n"
            f"🆔 <code>{payment['user_id']}</code>\n"
            f"💰 {payment['amount']:,} so'm\n"
            f"📅 {payment['created_at'].strftime('%d.%m.%Y %H:%M')}"
        ),
        reply_markup=admin_payment_action_kb(payment_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    payment_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE id = $1", payment_id
        )
        if not payment or payment['status'] != 'pending':
            await callback.answer("❌ To'lov topilmadi!", show_alert=True)
            return

        await conn.execute("""
            UPDATE payments SET status = 'confirmed',
            confirmed_by = $1, confirmed_at = NOW()
            WHERE id = $2
        """, callback.from_user.id, payment_id)

        await conn.execute("""
            UPDATE users SET balance = balance + $1 WHERE user_id = $2
        """, payment['amount'], payment['user_id'])

    reactivated = await reactivate_bots_if_balance(payment['user_id'])
    await notify_payment_confirmed(bot, payment['user_id'], payment['amount'])

    await callback.answer(
        f"✅ To'lov tasdiqlandi! {len(reactivated)} ta bot qayta ishga tushdi.",
        show_alert=True
    )
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    payment_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE id = $1", payment_id
        )
        if not payment:
            await callback.answer("❌ Topilmadi!", show_alert=True)
            return

        await conn.execute(
            "UPDATE payments SET status = 'rejected' WHERE id = $1", payment_id
        )

    await notify_payment_rejected(bot, payment['user_id'], payment['amount'])
    await callback.answer("❌ To'lov rad etildi!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass


# ═══════════════════════════════════════
# BOTLAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_bots")
async def admin_bots_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "🤖 <b>Botlar</b>",
        reply_markup=admin_bots_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.in_({"admin_bots_active", "admin_bots_inactive"}))
async def admin_bots_list_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    is_running = callback.data == "admin_bots_active"

    async with database.pool.acquire() as conn:
        bots = await conn.fetch("""
            SELECT b.id, b.bot_username, b.template_type, b.is_running,
                   u.full_name, u.user_id
            FROM bots b JOIN users u ON b.user_id = u.user_id
            WHERE b.is_running = $1
            ORDER BY b.created_at DESC
        """, is_running)

    if not bots:
        status_text = "faol" if is_running else "nofaol"
        await callback.answer(f"Bo'sh — {status_text} botlar yo'q", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    icons = {"quiz": "🎯", "shop": "🛒", "broadcaster": "📢",
             "referral": "👥", "kinobot": "🎬"}
    for b in bots:
        icon = icons.get(b['template_type'], "🤖")
        buttons.append([InlineKeyboardButton(
            text=f"{icon} @{b['bot_username'] or 'bot'} — {b['full_name']}",
            callback_data=f"admin_bot_detail_{b['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_bots")])

    title = "✅ Faol" if is_running else "❌ Nofaol"
    await callback.message.edit_text(
        f"{title} botlar: <b>{len(bots)} ta</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bot_detail_"))
async def admin_bot_detail_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        bot = await conn.fetchrow("""
            SELECT b.*, u.full_name FROM bots b
            JOIN users u ON b.user_id = u.user_id WHERE b.id = $1
        """, bot_id)

    if not bot:
        await callback.answer("❌ Topilmadi!", show_alert=True)
        return

    bot = dict(bot)
    status = "✅ Ishlayapti" if bot['is_running'] else "❌ To'xtatilgan"
    icons = {"quiz": "🎯", "shop": "🛒", "broadcaster": "📢",
             "referral": "👥", "kinobot": "🎬"}

    await callback.message.edit_text(
        f"{icons.get(bot['template_type'], '🤖')} <b>@{bot['bot_username'] or 'noma\'lum'}</b>\n\n"
        f"👤 Egasi: {bot['full_name']}\n"
        f"📊 Holat: {status}\n"
        f"📅 Yaratilgan: {bot['created_at'].strftime('%d.%m.%Y')}",
        reply_markup=admin_bot_action_kb(bot_id, bot['is_running']),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_start_bot_"))
async def admin_start_bot_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        bot_data = await conn.fetchrow("SELECT * FROM bots WHERE id = $1", bot_id)
        if not bot_data:
            await callback.answer("❌ Topilmadi!", show_alert=True)
            return
        await conn.execute("UPDATE bots SET is_running = TRUE WHERE id = $1", bot_id)

    from webhook.bot_manager import start_template_bot
    await start_template_bot(dict(bot_data))

    await callback.answer("✅ Bot ishga tushirildi!", show_alert=True)
    await admin_bot_detail_handler(callback)


@router.callback_query(F.data.startswith("admin_stop_bot_"))
async def admin_stop_bot_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        await conn.execute("UPDATE bots SET is_running = FALSE WHERE id = $1", bot_id)

    from webhook.bot_manager import stop_template_bot
    await stop_template_bot(bot_id)

    await callback.answer("⏹ Bot to'xtatildi!", show_alert=True)
    await admin_bot_detail_handler(callback)


@router.callback_query(F.data.startswith("admin_delete_bot_"))
async def admin_delete_bot_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    bot_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM bots WHERE id = $1", bot_id)

    from webhook.bot_manager import stop_template_bot
    await stop_template_bot(bot_id)

    await callback.answer("🗑️ Bot o'chirildi!", show_alert=True)
    await admin_bots_handler(callback)


# ═══════════════════════════════════════
# XABAR YUBORISH
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text(
        "📣 <b>Xabar yuborish</b>\n\nKimga yubormoqchisiz?",
        reply_markup=admin_broadcast_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_broadcast_"))
async def admin_broadcast_target(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    target = callback.data.replace("admin_broadcast_", "")
    await state.set_state(AdminStates.waiting_broadcast_text)
    await state.update_data(broadcast_target=target)

    target_names = {"all": "hammaga", "active": "faollarga", "trial": "triallarga"}
    await callback.message.edit_text(
        f"📣 <b>{target_names.get(target, target)}</b> yuboriladigan xabarni yozing:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    target = data.get('broadcast_target', 'all')
    await state.clear()

    await message.answer("📤 Yuborilmoqda...")
    result = await broadcast_message(bot, message.html_text, target)

    await message.answer(
        f"✅ <b>Yuborildi!</b>\n\n"
        f"✅ Muvaffaqiyatli: {result['success']}\n"
        f"❌ Yuborilmadi: {result['failed']}\n"
        f"📊 Jami: {result['total']}",
        reply_markup=admin_back_kb(),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_settings")
async def admin_settings_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    daily_price = await get_setting('daily_price') or '3000'
    trial_days = await get_setting('trial_days') or '7'
    referral_bonus = await get_setting('referral_bonus') or '5000'
    payment_card = await get_setting('payment_card') or 'Sozlanmagan'

    await callback.message.edit_text(
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"💰 Kunlik narx: <b>{int(daily_price):,} so'm</b>\n"
        f"🎁 Trial davomiyligi: <b>{trial_days} kun</b>\n"
        f"🔗 Referral bonus: <b>{int(referral_bonus):,} so'm</b>\n"
        f"💳 To'lov karta: <code>{payment_card}</code>",
        reply_markup=admin_settings_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_daily_price")
async def set_daily_price_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_daily_price)
    await callback.message.edit_text("💰 Yangi kunlik narxni kiriting (so'mda):")
    await callback.answer()


@router.message(AdminStates.waiting_daily_price)
async def save_daily_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text.replace(" ", ""))
        await set_setting('daily_price', str(amount))
        await state.clear()
        await message.answer(
            f"✅ Kunlik narx <b>{amount:,} so'm</b> ga o'zgartirildi.",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")


@router.callback_query(F.data == "admin_set_trial_days")
async def set_trial_days_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_trial_days)
    await callback.message.edit_text("🎁 Trial davomiyligini kiriting (kunlarda):")
    await callback.answer()


@router.message(AdminStates.waiting_trial_days)
async def save_trial_days(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        days = int(message.text.strip())
        await set_setting('trial_days', str(days))
        await state.clear()
        await message.answer(f"✅ Trial davomiyligi <b>{days} kun</b> ga o'zgartirildi.", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")


@router.callback_query(F.data == "admin_set_referral_bonus")
async def set_referral_bonus_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_referral_bonus)
    await callback.message.edit_text("🔗 Referral bonus miqdorini kiriting (so'mda):")
    await callback.answer()


@router.message(AdminStates.waiting_referral_bonus)
async def save_referral_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text.replace(" ", ""))
        await set_setting('referral_bonus', str(amount))
        await state.clear()
        await message.answer(f"✅ Referral bonus <b>{amount:,} so'm</b> ga o'zgartirildi.", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")


@router.callback_query(F.data == "admin_set_payment_card")
async def set_payment_card_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_payment_card)
    await callback.message.edit_text("💳 To'lov karta raqamini kiriting:")
    await callback.answer()


@router.message(AdminStates.waiting_payment_card)
async def save_payment_card(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    card = message.text.strip()
    await set_setting('payment_card', card)
    await state.clear()
    await message.answer(f"✅ Karta raqami saqlandi: <code>{card}</code>", parse_mode="HTML")


@router.callback_query(F.data == "admin_toggle_maintenance")
async def toggle_maintenance_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    current = await get_setting('maintenance_mode')
    new_value = 'false' if current == 'true' else 'true'
    await set_setting('maintenance_mode', new_value)
    status = "✅ Yoqildi" if new_value == 'true' else "❌ O'chirildi"
    await callback.answer(f"🔧 Texnik ishlar: {status}", show_alert=True)
    await admin_settings_handler(callback)


# ═══════════════════════════════════════
# MAJBURIY KANALLAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "admin_channels")
async def admin_channels_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    async with database.pool.acquire() as conn:
        channels = await conn.fetch(
            "SELECT * FROM required_channels WHERE is_active = TRUE"
        )
    channels_list = [dict(c) for c in channels]
    await callback.message.edit_text(
        f"📢 <b>Majburiy kanallar ({len(channels_list)} ta)</b>",
        reply_markup=admin_channels_kb(channels_list),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_channel")
async def admin_add_channel_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_channel_id)
    await callback.message.edit_text(
        "📢 Kanal ID ni kiriting:\n\n"
        "Masalan: <code>@mening_kanalim</code> yoki <code>-1001234567890</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_channel_id)
async def channel_id_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(channel_id=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_name)
    await message.answer("📝 Kanal nomini kiriting (tugmada ko'rinadigan nom):")


@router.message(AdminStates.waiting_channel_name)
async def channel_name_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(channel_name=message.text.strip())
    await state.set_state(AdminStates.waiting_channel_url)
    await message.answer("🔗 Kanal URL ni kiriting:\n\nMasalan: <code>https://t.me/mening_kanalim</code>", parse_mode="HTML")


@router.message(AdminStates.waiting_channel_url)
async def channel_url_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO required_channels (channel_id, channel_name, channel_url)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_id) DO UPDATE
            SET channel_name = $2, channel_url = $3, is_active = TRUE
        """, data['channel_id'], data['channel_name'], message.text.strip())

    await message.answer(
        f"✅ Kanal qo'shildi!\n\n"
        f"📢 {data['channel_name']}\n"
        f"🆔 {data['channel_id']}",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("admin_del_channel_"))
async def admin_del_channel_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    channel_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute(
            "UPDATE required_channels SET is_active = FALSE WHERE id = $1",
            channel_id
        )
    await callback.answer("✅ Kanal o'chirildi!", show_alert=True)
    await admin_channels_handler(callback)
