from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta

import database
from database import pool
from database import get_setting
from keyboards.main_menu import main_menu_kb, subscription_check_kb, back_to_main_kb
from utils.subscription import check_user_subscription
from config import ADMIN_ID

router = Router()


# ═══════════════════════════════════════
# YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════

async def get_or_create_user(user_id: int, username: str, full_name: str) -> dict:
    """Foydalanuvchini olish yoki yaratish"""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        if not user:
            trial_days = int(await get_setting('trial_days') or 7)
            trial_ends = datetime.now() + timedelta(days=trial_days)
            await conn.execute("""
                INSERT INTO users (user_id, username, full_name, trial_ends_at)
                VALUES ($1, $2, $3, $4)
            """, user_id, username, full_name, trial_ends)
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
        return dict(user)


async def get_referral_from_args(args: str) -> int | None:
    """Start argumentidan referral ID olish"""
    if args and args.startswith("ref_"):
        try:
            return int(args.split("_")[1])
        except (ValueError, IndexError):
            return None
    return None


async def apply_referral_bonus(referrer_id: int, new_user_id: int):
    """Referral bonus berish"""
    if referrer_id == new_user_id:
        return

    referral_enabled = await get_setting('referral_enabled')
    if referral_enabled != 'true':
        return

    async with pool.acquire() as conn:
        exists = await conn.fetchval("""
            SELECT id FROM referrals WHERE referred_id = $1
        """, new_user_id)
        if exists:
            return

        referrer = await conn.fetchrow(
            "SELECT user_id FROM users WHERE user_id = $1", referrer_id
        )
        if not referrer:
            return

        bonus = int(await get_setting('referral_bonus') or 5000)

        await conn.execute("""
            UPDATE users SET balance = balance + $1 WHERE user_id = $2
        """, bonus, referrer_id)

        await conn.execute("""
            INSERT INTO referrals (referrer_id, referred_id, bonus_amount)
            VALUES ($1, $2, $3)
        """, referrer_id, new_user_id, bonus)

        await conn.execute("""
            UPDATE users SET referred_by = $1 WHERE user_id = $2
        """, referrer_id, new_user_id)


async def send_main_menu(target, user: dict, state: FSMContext = None):
    """Asosiy menyuni yuborish — Reply Keyboard"""
    if state:
        await state.clear()

    trial_active = (
        user['trial_ends_at'] and
        user['trial_ends_at'] > datetime.now()
    )

    if trial_active:
        days_left = (user['trial_ends_at'] - datetime.now()).days + 1
        trial_text = f"🎁 Trial: <b>{days_left} kun</b> qoldi\n"
    else:
        trial_text = ""

    text = (
        f"👋 Xush kelibsiz, <b>{user['full_name']}</b>!\n\n"
        f"{trial_text}"
        f"💰 Balans: <b>{user['balance']:,} so'm</b>\n\n"
        f"Quyidagi tugmalardan birini tanlang:"
    )

    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════

@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or "Foydalanuvchi"

    await state.clear()

    async with pool.acquire() as conn:
        banned = await conn.fetchval(
            "SELECT is_banned FROM users WHERE user_id = $1", user_id
        )
        if banned:
            await message.answer("🚫 Siz bloklangansiz. Admin bilan bog'laning.")
            return

    is_subscribed, not_subscribed = await check_user_subscription(bot, user_id)
    if not is_subscribed:
        channels_text = "\n".join([f"• {ch['channel_name']}" for ch in not_subscribed])
        await message.answer(
            f"⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
            f"{channels_text}",
            reply_markup=subscription_check_kb(not_subscribed),
            parse_mode="HTML"
        )
        return

    args = message.text.split()[-1] if len(message.text.split()) > 1 else ""
    referrer_id = await get_referral_from_args(args)

    is_new_user = False
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT user_id FROM users WHERE user_id = $1", user_id
        )
        if not exists:
            is_new_user = True

    user = await get_or_create_user(user_id, username, full_name)

    if is_new_user and referrer_id:
        await apply_referral_bonus(referrer_id, user_id)

    await send_main_menu(message, user, state)


@router.callback_query(F.data == "check_subscription")
async def check_subscription_handler(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id

    is_subscribed, not_subscribed = await check_user_subscription(bot, user_id)

    if not is_subscribed:
        channels_text = "\n".join([f"• {ch['channel_name']}" for ch in not_subscribed])
        await callback.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        await callback.message.edit_text(
            f"⚠️ Quyidagi kanallarga obuna bo'ling:\n\n{channels_text}",
            reply_markup=subscription_check_kb(not_subscribed),
            parse_mode="HTML"
        )
        return

    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )

    if not user:
        user = await get_or_create_user(
            user_id,
            callback.from_user.username or "",
            callback.from_user.full_name or "Foydalanuvchi"
        )

    await callback.answer("✅ Obuna tasdiqlandi!")
    await send_main_menu(callback, dict(user), state)


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", callback.from_user.id
        )
    if user:
        await send_main_menu(callback, dict(user))
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    text = (
        "📞 <b>Yordam</b>\n\n"
        "❓ <b>Tez-tez so'raladigan savollar:</b>\n\n"
        "▪️ <b>Bot yaratish qancha turadi?</b>\n"
        "Har bir bot uchun kuniga 3,000 so'm yechiladi.\n\n"
        "▪️ <b>Trial nima?</b>\n"
        "Birinchi 7 kun bepul — 1 ta bot yaratishingiz mumkin.\n\n"
        "▪️ <b>Balans tugasa nima bo'ladi?</b>\n"
        "Bot to'xtatiladi. Balans to'ldirilgach qayta ishga tushadi.\n\n"
        "▪️ <b>Nechta bot yaratish mumkin?</b>\n"
        "Cheksiz — har biri uchun alohida 3,000 so'm/kun.\n\n"
        "👨‍💻 Admin bilan bog'lanish: @Createrbot_admin"
    )
    await callback.message.edit_text(
        text,
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# REPLY KEYBOARD TUGMALARI
# ═══════════════════════════════════════

@router.message(F.text == "🆕 Bot yaratish")
async def reply_create_bot(message: Message):
    from keyboards.main_menu import template_select_kb
    from utils.billing import can_create_bot
    
    user_id = message.from_user.id
    can, reason = await can_create_bot(user_id)
    if not can:
        await message.answer(
            f"❌ <b>Bot yaratib bo'lmaydi</b>\n\n{reason}",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML"
        )
        return
    await message.answer(
        "🆕 <b>Bot yaratish</b>\n\nQaysi turdagi bot yaratmoqchisiz?",
        reply_markup=template_select_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "📋 Mening botlarim")
async def reply_my_bots(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    async with pool.acquire() as conn:
        bots = await conn.fetch("""
            SELECT id, bot_username, template_type, is_running, created_at
            FROM bots WHERE user_id = $1
            ORDER BY created_at DESC
        """, message.from_user.id)

    if not bots:
        await message.answer(
            "🤖 <b>Mening botlarim</b>\n\n"
            "Hali birorta bot yaratmadingiz.\n"
            "«🆕 Bot yaratish» tugmasini bosing.",
            reply_markup=back_to_main_kb(),
            parse_mode="HTML"
        )
        return

    bots_list = [dict(b) for b in bots]
    running = sum(1 for b in bots_list if b['is_running'])
    
    buttons = []
    for bot in bots_list:
        status = "✅" if bot['is_running'] else "⏸"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {bot['bot_username']}",
            callback_data=f"bot_detail_{bot['id']}"  
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="main_menu")])
    
    await message.answer(
        f"🤖 <b>Mening botlarim</b>\n\n"
        f"Jami: <b>{len(bots_list)} ta</b> | Faol: <b>{running} ta</b>\n\n"
        f"Botni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.message(F.text == "💰 Balans")
async def reply_balance(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", message.from_user.id
        )
        bots_count = await conn.fetchval("""
            SELECT COUNT(*) FROM bots
            WHERE user_id = $1 AND is_running = TRUE
        """, message.from_user.id)

    trial_active = (
        user['trial_ends_at'] and user['trial_ends_at'] > datetime.now()
    )
    if trial_active:
        days_left = (user['trial_ends_at'] - datetime.now()).days + 1
        trial_text = f"🎁 Trial: <b>{days_left} kun</b> qoldi\n"
    else:
        trial_text = ""

    daily_price = await get_setting('daily_price') or '3000'
    daily_total = int(daily_price) * (bots_count or 0)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Balans to'ldirish", callback_data="topup_balance")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="main_menu")],
    ])

    await message.answer(
        f"💰 <b>Balans</b>\n\n"
        f"{trial_text}"
        f"💵 Joriy balans: <b>{user['balance']:,} so'm</b>\n"
        f"🤖 Faol botlar: <b>{bots_count} ta</b>\n"
        f"📊 Kunlik to'lov: <b>{daily_total:,} so'm</b>\n\n"
        f"Balansni to'ldirish uchun tugmani bosing 👇",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.message(F.text == "🔗 Do'st taklif qilish")
async def reply_referral(message: Message, bot: Bot):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    async with pool.acquire() as conn:
        refs_count = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", user_id
        )
        total_earned = await conn.fetchval(
            "SELECT COALESCE(SUM(bonus_amount), 0) FROM referrals WHERE referrer_id = $1",
            user_id
        )

    bonus = await get_setting('referral_bonus') or '5000'

    await message.answer(
        f"🔗 <b>Do'st taklif qilish</b>\n\n"
        f"Har bir do'stingiz uchun <b>{int(bonus):,} so'm</b> bonus!\n\n"
        f"👥 Taklif qilganlar: <b>{refs_count} ta</b>\n"
        f"💰 Jami ishlagan: <b>{total_earned:,} so'm</b>\n\n"
        f"🔗 Havolangiz:\n<code>{referral_link}</code>",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "📞 Yordam")
async def reply_help(message: Message):
    await message.answer(
        "📞 <b>Yordam</b>\n\n"
        "▪️ <b>Bot yaratish qancha turadi?</b>\n"
        "Har bir bot uchun kuniga 3,000 so'm.\n\n"
        "▪️ <b>Trial nima?</b>\n"
        "Birinchi 7 kun bepul — 1 ta bot bepul.\n\n"
        "▪️ <b>Balans tugasa nima bo'ladi?</b>\n"
        "Bot to'xtatiladi. To'ldirilgach qayta ishga tushadi.\n\n"
        "▪️ <b>Nechta bot yaratish mumkin?</b>\n"
        "Cheksiz — har biri 3,000 so'm/kun.\n\n"
        "👨‍💻 Admin: @createrbot_admin",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )
