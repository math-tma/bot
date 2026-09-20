from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

import database
from database import pool
from templates.referral.keyboards import (
    subscription_kb, phone_kb, main_menu_kb, withdraw_kb,
    back_main_kb, admin_main_kb, admin_withdrawal_kb,
    admin_settings_kb, admin_user_kb, back_admin_kb
)

router = Router()


class RefStates(StatesGroup):
    waiting_phone = State()
    waiting_withdraw_amount = State()
    waiting_withdraw_card = State()
    # Admin
    set_bonus = State()
    set_min_withdraw = State()
    set_card = State()
    broadcast_text = State()
    add_channel_id = State()
    add_channel_name = State()
    add_channel_url = State()


# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════

async def get_bot_row(bot: Bot) -> dict | None:
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_username = $1",
            bot_info.username
        )
        return dict(row) if row else None


async def check_sub(bot: Bot, user_id: int, bot_id: int) -> tuple[bool, list]:
    async with database.pool.acquire() as conn:
        channels = await conn.fetch(
            "SELECT * FROM bot_required_channels WHERE bot_id = $1", bot_id
        )
    if not channels:
        return True, []
    not_sub = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch['channel_id'], user_id)
            if m.status in ['left', 'kicked', 'banned']:
                not_sub.append(dict(ch))
        except Exception:
            not_sub.append(dict(ch))
    return len(not_sub) == 0, not_sub


async def get_settings(bot_id: int) -> dict:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM referral_bot_settings WHERE bot_id = $1", bot_id
        )
        return dict(row) if row else {
            "bonus_per_referral": 1000,
            "min_withdrawal": 10000,
            "payment_card": ""
        }


async def is_admin_user(bot: Bot, user_id: int) -> bool:
    row = await get_bot_row(bot)
    return row and row['admin_id'] == user_id


async def get_user(bot_id: int, user_id: int) -> dict | None:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM referral_bot_users
            WHERE bot_id = $1 AND user_id = $2
        """, bot_id, user_id)
        return dict(row) if row else None


# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════

@router.message(CommandStart())
async def ref_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    row = await get_bot_row(bot)
    if not row:
        return
    bot_id = row['id']
    user_id = message.from_user.id

    # Obuna tekshirish
    ok, not_sub = await check_sub(bot, user_id, bot_id)
    if not ok:
        await message.answer(
            "📢 Botdan foydalanish uchun obuna bo'ling:",
            reply_markup=subscription_kb(not_sub)
        )
        return

    # Mavjud foydalanuvchi
    user = await get_user(bot_id, user_id)
    if user:
        if user['is_banned']:
            await message.answer("🚫 Siz bloklangansiz.")
            return
        await show_main_menu(message, user, is_admin=(row['admin_id'] == user_id))
        return

    # Yangi foydalanuvchi — referral tekshirish
    args = message.text.split()[-1] if len(message.text.split()) > 1 else ""
    referrer_id = None
    if args.startswith("ref_"):
        try:
            referrer_id = int(args.split("_")[1])
            if referrer_id == user_id:
                referrer_id = None
        except (ValueError, IndexError):
            referrer_id = None

    await state.update_data(referrer_id=referrer_id)
    await state.set_state(RefStates.waiting_phone)

    await message.answer(
        "👋 <b>Xush kelibsiz!</b>\n\n"
        "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring 👇",
        reply_markup=phone_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ref_check_sub")
async def ref_check_sub(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return
    ok, not_sub = await check_sub(bot, callback.from_user.id, row['id'])
    if not ok:
        await callback.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    await callback.answer("✅ Tasdiqlandi!")
    await callback.message.edit_text(
        "👋 <b>Xush kelibsiz!</b>\n\nTelefon raqamingizni yuboring 👇",
        parse_mode="HTML"
    )


@router.message(RefStates.waiting_phone, F.contact)
async def ref_phone_received(message: Message, state: FSMContext, bot: Bot):
    row = await get_bot_row(bot)
    bot_id = row['id']
    user_id = message.from_user.id
    phone = message.contact.phone_number
    data = await state.get_data()
    referrer_id = data.get('referrer_id')

    # Telefon raqam allaqachon bormi?
    async with database.pool.acquire() as conn:
        phone_exists = await conn.fetchval("""
            SELECT id FROM referral_bot_users
            WHERE bot_id = $1 AND phone = $2
        """, bot_id, phone)

        if phone_exists:
            await message.answer(
                "❌ Bu telefon raqam allaqachon ro'yxatdan o'tgan!",
                reply_markup=main_menu_kb()
            )
            await state.clear()
            return

        # Foydalanuvchini yaratish
        await conn.execute("""
            INSERT INTO referral_bot_users
            (bot_id, user_id, username, full_name, phone, referred_by)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (bot_id, user_id) DO NOTHING
        """, bot_id, user_id,
            message.from_user.username or "",
            message.from_user.full_name or "",
            phone, referrer_id
        )

        # Referral bonus
        if referrer_id:
            settings = await get_settings(bot_id)
            bonus = settings['bonus_per_referral']

            # Referrer mavjudmi?
            referrer_exists = await conn.fetchval("""
                SELECT id FROM referral_bot_users
                WHERE bot_id = $1 AND user_id = $2
            """, bot_id, referrer_id)

            if referrer_exists:
                await conn.execute("""
                    UPDATE referral_bot_users
                    SET balance = balance + $1
                    WHERE bot_id = $2 AND user_id = $3
                """, bonus, bot_id, referrer_id)

                # Referrerga xabar
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 <b>Yangi referal!</b>\n\n"
                        f"Sizning havolangiz orqali yangi odam ro'yxatdan o'tdi.\n"
                        f"💰 Balansingizga <b>+{bonus:,} so'm</b> qo'shildi!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    await state.clear()

    user = await get_user(bot_id, user_id)
    await show_main_menu(message, user, is_new=True, is_admin=(row['admin_id'] == user_id))


@router.message(RefStates.waiting_phone)
async def ref_phone_wrong(message: Message):
    await message.answer(
        "❌ Iltimos, telefon raqamni tugma orqali yuboring 👇",
        reply_markup=phone_kb()
    )


async def show_main_menu(target, user: dict, is_new: bool = False, is_admin: bool = False):
    text = ""
    if is_new:
        text = "✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n"

    text += (
        f"👤 <b>{user['full_name'] or 'Foydalanuvchi'}</b>\n\n"
        f"💰 Balans: <b>{user['balance']:,} so'm</b>"
    )

    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu_kb(is_admin), parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=main_menu_kb(is_admin), parse_mode="HTML")


@router.callback_query(F.data == "ref_main")
async def ref_main_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    row = await get_bot_row(bot)
    user = await get_user(row['id'], callback.from_user.id)
    if not user:
        await callback.answer()
        return
    await show_main_menu(callback, user, is_admin=(row['admin_id'] == callback.from_user.id))
    await callback.answer()


# ═══════════════════════════════════════
# FOYDALANUVCHI MENYULAR
# ═══════════════════════════════════════

@router.callback_query(F.data == "ref_link")
async def ref_link_handler(callback: CallbackQuery, bot: Bot):
    bot_info = await bot.get_me()
    row = await get_bot_row(bot)
    user = await get_user(row['id'], callback.from_user.id)
    if not user:
        return

    link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"

    async with database.pool.acquire() as conn:
        refs_count = await conn.fetchval("""
            SELECT COUNT(*) FROM referral_bot_users
            WHERE bot_id = $1 AND referred_by = $2
        """, row['id'], callback.from_user.id)

    settings = await get_settings(row['id'])

    await callback.message.edit_text(
        f"🔗 <b>Referral havola</b>\n\n"
        f"Har taklif uchun: <b>{settings['bonus_per_referral']:,} so'm</b>\n"
        f"Taklif qilganlar: <b>{refs_count} ta</b>\n\n"
        f"🔗 Havolangiz:\n<code>{link}</code>\n\n"
        f"Do'stlaringizga yuboring va bonus oling! 🎉",
        reply_markup=back_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_balance")
async def ref_balance_handler(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    user = await get_user(row['id'], callback.from_user.id)
    if not user:
        return

    async with database.pool.acquire() as conn:
        refs_count = await conn.fetchval("""
            SELECT COUNT(*) FROM referral_bot_users
            WHERE bot_id = $1 AND referred_by = $2
        """, row['id'], callback.from_user.id)

        total_withdrawn = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0)
            FROM referral_bot_withdrawals
            WHERE bot_id = $1 AND user_id = $2 AND status = 'confirmed'
        """, row['id'], callback.from_user.id)

    settings = await get_settings(row['id'])

    await callback.message.edit_text(
        f"💰 <b>Balans</b>\n\n"
        f"💵 Joriy balans: <b>{user['balance']:,} so'm</b>\n"
        f"👥 Referallar: <b>{refs_count} ta</b>\n"
        f"✅ Yechilgan: <b>{total_withdrawn:,} so'm</b>\n\n"
        f"💸 Minimal yechish: <b>{settings['min_withdrawal']:,} so'm</b>",
        reply_markup=back_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_leaderboard")
async def ref_leaderboard_handler(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        top = await conn.fetch("""
            SELECT u.full_name, u.username,
                   COUNT(r.id) as refs_count,
                   u.balance
            FROM referral_bot_users u
            LEFT JOIN referral_bot_users r ON r.referred_by = u.user_id AND r.bot_id = u.bot_id
            WHERE u.bot_id = $1
            GROUP BY u.user_id, u.full_name, u.username, u.balance
            ORDER BY refs_count DESC, u.balance DESC
            LIMIT 10
        """, row['id'])

    if not top:
        await callback.answer("🏆 Hali ma'lumotlar yo'q!", show_alert=True)
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = []
    for i, u in enumerate(top):
        name = u['full_name'] or f"@{u['username']}" or "Anonim"
        lines.append(
            f"{medals[i]} {name} — "
            f"{u['refs_count']} referal | "
            f"{u['balance']:,} so'm"
        )

    await callback.message.edit_text(
        "🏆 <b>Leaderboard (Top 10)</b>\n\n" + "\n".join(lines),
        reply_markup=back_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_withdraw")
async def ref_withdraw_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    row = await get_bot_row(bot)
    user = await get_user(row['id'], callback.from_user.id)
    if not user:
        return

    settings = await get_settings(row['id'])
    min_w = settings['min_withdrawal']

    if user['balance'] < min_w:
        await callback.answer(
            f"❌ Minimal yechish: {min_w:,} so'm\n"
            f"Sizda: {user['balance']:,} so'm",
            show_alert=True
        )
        return

    await state.set_state(RefStates.waiting_withdraw_amount)
    await state.update_data(bot_id=row['id'])

    await callback.message.edit_text(
        f"💸 <b>Pul yechish</b>\n\n"
        f"💵 Balansingiz: <b>{user['balance']:,} so'm</b>\n"
        f"📊 Minimal: <b>{min_w:,} so'm</b>\n\n"
        f"Yechmoqchi bo'lgan miqdorni kiriting:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(RefStates.waiting_withdraw_amount)
async def withdraw_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return

    data = await state.get_data()
    user = await get_user(data['bot_id'], message.from_user.id)
    settings = await get_settings(data['bot_id'])

    if amount < settings['min_withdrawal']:
        await message.answer(
            f"❌ Minimal yechish: {settings['min_withdrawal']:,} so'm"
        )
        return

    if amount > user['balance']:
        await message.answer(
            f"❌ Balansingiz yetarli emas!\n"
            f"Sizda: {user['balance']:,} so'm"
        )
        return

    await state.update_data(withdraw_amount=amount)
    await state.set_state(RefStates.waiting_withdraw_card)
    await message.answer(
        f"💳 Karta raqamingizni kiriting:\n"
        f"Yechish miqdori: <b>{amount:,} so'm</b>",
        parse_mode="HTML"
    )


@router.message(RefStates.waiting_withdraw_card)
async def withdraw_card(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    card = message.text.strip()
    user_id = message.from_user.id
    bot_id = data['bot_id']
    amount = data['withdraw_amount']

    async with database.pool.acquire() as conn:
        # Balansdan yechish
        await conn.execute("""
            UPDATE referral_bot_users
            SET balance = balance - $1
            WHERE bot_id = $2 AND user_id = $3
        """, amount, bot_id, user_id)

        # So'rov yaratish
        w_id = await conn.fetchval("""
            INSERT INTO referral_bot_withdrawals
            (bot_id, user_id, amount, card_number)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, bot_id, user_id, amount, card)

    await state.clear()

    row = await get_bot_row(bot)
    user = await get_user(bot_id, user_id)

    await message.answer(
        f"✅ <b>So'rov yuborildi!</b>\n\n"
        f"💰 Miqdor: <b>{amount:,} so'm</b>\n"
        f"💳 Karta: <code>{card}</code>\n\n"
        f"⏳ Admin 24 soat ichida ko'rib chiqadi.",
        reply_markup=back_main_kb(),
        parse_mode="HTML"
    )

    # Adminga xabar
    try:
        await bot.send_message(
            row['admin_id'],
            f"💸 <b>Yechish so'rovi #{w_id}</b>\n\n"
            f"👤 {user['full_name']}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"💰 {amount:,} so'm\n"
            f"💳 <code>{card}</code>",
            reply_markup=admin_withdrawal_kb(w_id),
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "ref_help")
async def ref_help_handler(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    settings = await get_settings(row['id'])

    await callback.message.edit_text(
        f"ℹ️ <b>Yordam</b>\n\n"
        f"🔗 Do'stingizga havolani yuboring\n"
        f"👥 U ro'yxatdan o'tsa — bonus olasiz\n"
        f"💰 Har referal uchun: <b>{settings['bonus_per_referral']:,} so'm</b>\n"
        f"💸 Minimal yechish: <b>{settings['min_withdrawal']:,} so'm</b>\n\n"
        f"❓ Savollar uchun adminga murojaat qiling.",
        reply_markup=back_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════

@router.message(Command("admin"))
async def ref_admin(message: Message, bot: Bot):
    if not await is_admin_user(bot, message.from_user.id):
        return
    await message.answer(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ref_admin")
async def ref_admin_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Yechish so'rovlari ──

@router.callback_query(F.data == "ref_admin_withdrawals")
async def ref_admin_withdrawals(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        withdrawals = await conn.fetch("""
            SELECT w.id, w.user_id, w.amount, w.card_number,
                   u.full_name, u.username
            FROM referral_bot_withdrawals w
            JOIN referral_bot_users u ON w.user_id = u.user_id AND w.bot_id = u.bot_id
            WHERE w.bot_id = $1 AND w.status = 'pending'
            ORDER BY w.created_at ASC
        """, row['id'])

    if not withdrawals:
        await callback.answer("✅ Kutayotgan so'rovlar yo'q!", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for w in withdrawals:
        buttons.append([InlineKeyboardButton(
            text=f"#{w['id']} | {w['full_name']} | {w['amount']:,} so'm",
            callback_data=f"ref_view_w_{w['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_admin")])

    await callback.message.edit_text(
        f"💸 <b>Kutayotgan so'rovlar: {len(withdrawals)} ta</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ref_view_w_"))
async def ref_view_withdrawal(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    w_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        w = await conn.fetchrow("""
            SELECT w.*, u.full_name, u.username
            FROM referral_bot_withdrawals w
            JOIN referral_bot_users u ON w.user_id = u.user_id AND w.bot_id = u.bot_id
            WHERE w.id = $1
        """, w_id)

    if not w:
        await callback.answer("❌ Topilmadi!", show_alert=True)
        return

    await callback.message.edit_text(
        f"💸 <b>Yechish so'rovi #{w_id}</b>\n\n"
        f"👤 {w['full_name']}\n"
        f"🆔 <code>{w['user_id']}</code>\n"
        f"💰 {w['amount']:,} so'm\n"
        f"💳 <code>{w['card_number']}</code>",
        reply_markup=admin_withdrawal_kb(w_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ref_confirm_w_"))
async def ref_confirm_withdrawal(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    w_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        w = await conn.fetchrow(
            "SELECT * FROM referral_bot_withdrawals WHERE id = $1", w_id
        )
        if not w or w['status'] != 'pending':
            await callback.answer("❌ Topilmadi!", show_alert=True)
            return

        await conn.execute("""
            UPDATE referral_bot_withdrawals
            SET status = 'confirmed', confirmed_at = NOW()
            WHERE id = $1
        """, w_id)

    await callback.answer("✅ Tasdiqlandi!", show_alert=True)

    try:
        await bot.send_message(
            w['user_id'],
            f"✅ <b>Yechish tasdiqlandi!</b>\n\n"
            f"💰 {w['amount']:,} so'm\n"
            f"💳 {w['card_number']}\n\n"
            f"Pul tez orada kartangizga o'tkaziladi.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("ref_reject_w_"))
async def ref_reject_withdrawal(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    w_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        w = await conn.fetchrow(
            "SELECT * FROM referral_bot_withdrawals WHERE id = $1", w_id
        )
        if not w:
            await callback.answer("❌ Topilmadi!", show_alert=True)
            return

        await conn.execute(
            "UPDATE referral_bot_withdrawals SET status = 'rejected' WHERE id = $1", w_id
        )
        # Balansni qaytarish
        await conn.execute("""
            UPDATE referral_bot_users SET balance = balance + $1
            WHERE bot_id = $2 AND user_id = $3
        """, w['amount'], row['id'], w['user_id'])

    await callback.answer("❌ Rad etildi, balans qaytarildi!", show_alert=True)

    try:
        await bot.send_message(
            w['user_id'],
            f"❌ <b>Yechish rad etildi.</b>\n\n"
            f"💰 {w['amount']:,} so'm balansingizga qaytarildi.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass


# ── Foydalanuvchilar ──

@router.callback_query(F.data == "ref_admin_users")
async def ref_admin_users(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT user_id, full_name, username, balance, is_banned
            FROM referral_bot_users WHERE bot_id = $1
            ORDER BY balance DESC LIMIT 30
        """, row['id'])

    if not users:
        await callback.answer("👥 Hali foydalanuvchilar yo'q!", show_alert=True)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for u in users:
        ban_icon = "🚫" if u['is_banned'] else "✅"
        buttons.append([InlineKeyboardButton(
            text=f"{ban_icon} {u['full_name'] or u['user_id']} — {u['balance']:,} so'm",
            callback_data=f"ref_admin_user_{u['user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_admin")])

    await callback.message.edit_text(
        f"👥 <b>Foydalanuvchilar ({len(users)} ta)</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ref_admin_user_"))
async def ref_admin_user_detail(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)
    user = await get_user(row['id'], user_id)

    if not user:
        await callback.answer("❌ Topilmadi!", show_alert=True)
        return

    status = "🚫 Banlangan" if user['is_banned'] else "✅ Faol"

    async with database.pool.acquire() as conn:
        refs = await conn.fetchval("""
            SELECT COUNT(*) FROM referral_bot_users
            WHERE bot_id = $1 AND referred_by = $2
        """, row['id'], user_id)

    await callback.message.edit_text(
        f"👤 <b>{user['full_name']}</b>\n\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📞 {user['phone']}\n"
        f"💰 Balans: <b>{user['balance']:,} so'm</b>\n"
        f"👥 Referallar: <b>{refs}</b>\n"
        f"📊 Holat: {status}",
        reply_markup=admin_user_kb(user_id, user['is_banned']),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ref_ban_"))
async def ref_ban_user(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE referral_bot_users SET is_banned = TRUE
            WHERE bot_id = $1 AND user_id = $2
        """, row['id'], user_id)
    await callback.answer("🚫 Banlandi!", show_alert=True)
    await ref_admin_user_detail(callback, bot)


@router.callback_query(F.data.startswith("ref_unban_"))
async def ref_unban_user(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE referral_bot_users SET is_banned = FALSE
            WHERE bot_id = $1 AND user_id = $2
        """, row['id'], user_id)
    await callback.answer("✅ Ban olib tashlandi!", show_alert=True)
    await ref_admin_user_detail(callback, bot)


# ── Sozlamalar ──

@router.callback_query(F.data == "ref_admin_settings")
async def ref_admin_settings(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    s = await get_settings(row['id'])

    await callback.message.edit_text(
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"💰 Bonus: <b>{s['bonus_per_referral']:,} so'm</b>\n"
        f"💸 Min yechish: <b>{s['min_withdrawal']:,} so'm</b>\n"
        f"💳 Karta: <code>{s['payment_card'] or 'Sozlanmagan'}</code>",
        reply_markup=admin_settings_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_set_bonus")
async def ref_set_bonus(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(RefStates.set_bonus)
    await callback.message.edit_text("💰 Yangi bonus miqdorini kiriting (so'mda):")
    await callback.answer()


@router.message(RefStates.set_bonus)
async def save_bonus(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.replace(" ", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE referral_bot_settings SET bonus_per_referral = $1 WHERE bot_id = $2
        """, amount, row['id'])
    await state.clear()
    await message.answer(
        f"✅ Bonus <b>{amount:,} so'm</b> ga o'zgartirildi.",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ref_set_min_withdraw")
async def ref_set_min_w(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(RefStates.set_min_withdraw)
    await callback.message.edit_text("💸 Minimal yechish miqdorini kiriting:")
    await callback.answer()


@router.message(RefStates.set_min_withdraw)
async def save_min_w(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = int(message.text.replace(" ", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE referral_bot_settings SET min_withdrawal = $1 WHERE bot_id = $2
        """, amount, row['id'])
    await state.clear()
    await message.answer(
        f"✅ Minimal yechish <b>{amount:,} so'm</b> ga o'zgartirildi.",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ref_set_card")
async def ref_set_card(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(RefStates.set_card)
    await callback.message.edit_text("💳 To'lov karta raqamini kiriting:")
    await callback.answer()


@router.message(RefStates.set_card)
async def save_card(message: Message, state: FSMContext, bot: Bot):
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE referral_bot_settings SET payment_card = $1 WHERE bot_id = $2
        """, message.text.strip(), row['id'])
    await state.clear()
    await message.answer(
        f"✅ Karta saqlandi: <code>{message.text.strip()}</code>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


# ── Statistika ──

@router.callback_query(F.data == "ref_admin_stats")
async def ref_admin_stats(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    bot_id = row['id']

    async with database.pool.acquire() as conn:
        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM referral_bot_users WHERE bot_id = $1", bot_id
        )
        active_users = await conn.fetchval("""
            SELECT COUNT(*) FROM referral_bot_users
            WHERE bot_id = $1 AND is_banned = FALSE
        """, bot_id)
        pending_w = await conn.fetchval("""
            SELECT COUNT(*) FROM referral_bot_withdrawals
            WHERE bot_id = $1 AND status = 'pending'
        """, bot_id)
        total_paid = await conn.fetchval("""
            SELECT COALESCE(SUM(amount), 0) FROM referral_bot_withdrawals
            WHERE bot_id = $1 AND status = 'confirmed'
        """, bot_id)

    await callback.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"✅ Faollar: <b>{active_users}</b>\n"
        f"⏳ Kutayotgan to'lovlar: <b>{pending_w}</b>\n"
        f"💸 Jami to'langan: <b>{total_paid:,} so'm</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Xabar yuborish ──

@router.callback_query(F.data == "ref_admin_broadcast")
async def ref_broadcast_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(RefStates.broadcast_text)
    await callback.message.edit_text("📣 Barcha foydalanuvchilarga xabar yozing:")
    await callback.answer()


@router.message(RefStates.broadcast_text)
async def ref_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT user_id FROM referral_bot_users
            WHERE bot_id = $1 AND is_banned = FALSE
        """, row['id'])

    success, failed = 0, 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.html_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(
        f"✅ Yuborildi: {success}\n❌ Yuborilmadi: {failed}",
        reply_markup=back_admin_kb()
    )


# ── Kanallar ──

@router.callback_query(F.data == "ref_admin_channels")
async def ref_channels(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        channels = await conn.fetch(
            "SELECT id, channel_name FROM bot_required_channels WHERE bot_id = $1",
            row['id']
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {ch['channel_name']}",
            callback_data=f"ref_del_ch_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Qo'shish", callback_data="ref_add_ch")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_admin")])

    await callback.message.edit_text(
        f"📢 Majburiy kanallar ({len(channels)} ta)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ref_add_ch")
async def ref_add_ch(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(RefStates.add_channel_id)
    await callback.message.edit_text("📢 Kanal ID kiriting:")
    await callback.answer()


@router.message(RefStates.add_channel_id)
async def ref_ch_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text.strip())
    await state.set_state(RefStates.add_channel_name)
    await message.answer("📝 Kanal nomini kiriting:")


@router.message(RefStates.add_channel_name)
async def ref_ch_name(message: Message, state: FSMContext):
    await state.update_data(ch_name=message.text.strip())
    await state.set_state(RefStates.add_channel_url)
    await message.answer("🔗 Kanal URL kiriting:")


@router.message(RefStates.add_channel_url)
async def ref_ch_url(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_required_channels (bot_id, channel_id, channel_name, channel_url)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, row['id'], data['ch_id'], data['ch_name'], message.text.strip())
    await message.answer(
        f"✅ Kanal qo'shildi: <b>{data['ch_name']}</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("ref_del_ch_"))
async def ref_del_ch(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    ch_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM bot_required_channels WHERE id = $1", ch_id)
    await callback.answer("✅ O'chirildi!", show_alert=True)
    await ref_channels(callback, bot)
