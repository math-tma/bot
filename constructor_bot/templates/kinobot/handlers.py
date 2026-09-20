from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import logging

import database
from database import pool
from templates.kinobot.keyboards import (
    subscription_kb, admin_main_kb, admin_channels_kb, back_admin_kb
)

router = Router()
logger = logging.getLogger(__name__)


class KinoStates(StatesGroup):
    # Admin
    add_code = State()
    add_name = State()
    add_file = State()
    delete_code = State()
    broadcast_text = State()
    add_channel_id = State()
    add_channel_name = State()
    add_channel_url = State()


# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════

async def get_bot_id(token: str) -> int | None:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_token = $1", token
        )
        return row['id'] if row else None


async def check_subscription(bot: Bot, user_id: int, bot_id: int) -> tuple[bool, list]:
    async with database.pool.acquire() as conn:
        channels = await conn.fetch("""
            SELECT id, channel_id, channel_name, channel_url
            FROM bot_required_channels WHERE bot_id = $1
        """, bot_id)

    if not channels:
        return True, []

    not_subscribed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(dict(ch))
        except Exception as e:
            logger.warning(
                f"Kanal tekshirishda xato (channel_id={ch['channel_id']}, "
                f"user_id={user_id}): {e}"
            )
            not_subscribed.append(dict(ch))

    return len(not_subscribed) == 0, not_subscribed


async def register_user(bot_id: int, user_id: int, username: str):
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO kinobot_users (bot_id, user_id, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (bot_id, user_id) DO NOTHING
        """, bot_id, user_id, username)


async def is_banned(bot_id: int, user_id: int) -> bool:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT is_banned FROM kinobot_users
            WHERE bot_id = $1 AND user_id = $2
        """, bot_id, user_id)
        return row['is_banned'] if row else False


# ═══════════════════════════════════════
# FOYDALANUVCHI
# ═══════════════════════════════════════

@router.message(CommandStart())
async def kino_start(message: Message, bot: Bot):
    token = (await bot.get_me()).token if hasattr(bot, 'token') else None
    bot_info = await bot.get_me()

    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_username = $1",
            bot_info.username
        )
    if not bot_row:
        return

    bot_id = bot_row['id']
    user_id = message.from_user.id

    # Ban tekshirish
    if await is_banned(bot_id, user_id):
        await message.answer("🚫 Siz bloklangansiz.")
        return

    # Foydalanuvchini ro'yxatdan o'tkazish
    await register_user(bot_id, user_id, message.from_user.username or "")

    # Obuna tekshirish
    ok, not_sub = await check_subscription(bot, user_id, bot_id)
    if not ok:
        await message.answer(
            "📢 Botdan foydalanish uchun obuna bo'ling:",
            reply_markup=subscription_kb(not_sub)
        )
        return

    is_admin = bot_row['admin_id'] == user_id
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    admin_kb = None
    if is_admin:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Admin panel", callback_data="kino_admin")]
        ])

    await message.answer(
        "🎬 <b>Kino bot</b>\n\n"
        "Kino kodini yuboring va filmni oling!\n\n"
        "💡 Kino kodini kanalimizdan topishingiz mumkin.",
        reply_markup=admin_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "kino_check_sub")
async def kino_check_sub(callback: CallbackQuery, bot: Bot):
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_username = $1", bot_info.username
        )
    if not bot_row:
        return

    bot_id = bot_row['id']
    ok, not_sub = await check_subscription(bot, callback.from_user.id, bot_id)

    if not ok:
        await callback.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return

    await callback.answer("✅ Obuna tasdiqlandi!")

    is_admin = bot_row['admin_id'] == callback.from_user.id
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    admin_kb = None
    if is_admin:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Admin panel", callback_data="kino_admin")]
        ])

    await callback.message.edit_text(
        "🎬 <b>Kino bot</b>\n\n"
        "Kino kodini yuboring va filmni oling!\n\n"
        "💡 Kino kodini kanalimizdan topishingiz mumkin.",
        reply_markup=admin_kb,
        parse_mode="HTML"
    )


@router.message(F.text & ~F.text.startswith("/"))
async def kino_code_handler(message: Message, bot: Bot):
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_username = $1",
            bot_info.username
        )
    if not bot_row:
        return

    bot_id = bot_row['id']
    user_id = message.from_user.id

    # Ban tekshirish
    if await is_banned(bot_id, user_id):
        await message.answer("🚫 Siz bloklangansiz.")
        return

    # Obuna tekshirish
    ok, not_sub = await check_subscription(bot, user_id, bot_id)
    if not ok:
        await message.answer(
            "📢 Avval obuna bo'ling:",
            reply_markup=subscription_kb(not_sub)
        )
        return

    code = message.text.strip().lower()

    async with database.pool.acquire() as conn:
        movie = await conn.fetchrow("""
            SELECT name, file_id FROM kinobot_movies
            WHERE bot_id = $1 AND LOWER(code) = $2
        """, bot_id, code)

    if not movie:
        await message.answer(
            "❌ <b>Bunday kino mavjud emas!</b>\n\n"
            "Kodni to'g'ri yozganingizni tekshiring.",
            parse_mode="HTML"
        )
        return

    await message.answer_video(
        video=movie['file_id'],
        caption=f"🎬 <b>{movie['name']}</b>",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════

async def is_admin(bot: Bot, user_id: int) -> bool:
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT admin_id FROM bots WHERE bot_username = $1",
            bot_info.username
        )
        return row and row['admin_id'] == user_id


@router.message(Command("admin"))
async def kino_admin_panel(message: Message, bot: Bot):
    if not await is_admin(bot, message.from_user.id):
        return
    await message.answer(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "kino_admin")
async def kino_admin_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin(bot, callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Kino qo'shish ──

@router.callback_query(F.data == "kino_add")
async def kino_add_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin(bot, callback.from_user.id):
        return
    await state.set_state(KinoStates.add_code)
    await callback.message.edit_text(
        "🎬 <b>Kino qo'shish</b>\n\n"
        "Kino kodini kiriting:\n"
        "Masalan: <code>001</code> yoki <code>batman</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(KinoStates.add_code)
async def kino_add_code(message: Message, state: FSMContext):
    code = message.text.strip().lower()
    await state.update_data(code=code)
    await state.set_state(KinoStates.add_name)
    await message.answer(
        f"✅ Kod: <code>{code}</code>\n\n"
        f"Endi kino nomini kiriting:",
        parse_mode="HTML"
    )


@router.message(KinoStates.add_name)
async def kino_add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(KinoStates.add_file)
    await message.answer(
        "📹 Endi kino faylini yuboring (video yoki document):"
    )


@router.message(KinoStates.add_file, F.video | F.document)
async def kino_add_file(message: Message, state: FSMContext, bot: Bot):
    file_id = message.video.file_id if message.video else message.document.file_id
    data = await state.get_data()

    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        bot_id = bot_row['id']

        # Kod mavjudligini tekshirish
        exists = await conn.fetchval("""
            SELECT id FROM kinobot_movies
            WHERE bot_id = $1 AND code = $2
        """, bot_id, data['code'])

        if exists:
            await state.clear()
            await message.answer(
                f"❌ <code>{data['code']}</code> kodi allaqachon mavjud!\n"
                f"Boshqa kod tanlang.",
                parse_mode="HTML",
                reply_markup=back_admin_kb()
            )
            return

        await conn.execute("""
            INSERT INTO kinobot_movies (bot_id, code, name, file_id)
            VALUES ($1, $2, $3, $4)
        """, bot_id, data['code'], data['name'], file_id)

    await state.clear()
    await message.answer(
        f"✅ <b>Kino qo'shildi!</b>\n\n"
        f"📌 Kod: <code>{data['code']}</code>\n"
        f"🎬 Nom: {data['name']}",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.message(KinoStates.add_file)
async def kino_add_file_wrong(message: Message):
    await message.answer("❌ Iltimos, video yoki fayl yuboring.")


# ── Kino o'chirish ──

@router.callback_query(F.data == "kino_delete")
async def kino_delete_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin(bot, callback.from_user.id):
        return
    await state.set_state(KinoStates.delete_code)
    await callback.message.edit_text(
        "🗑️ O'chirmoqchi bo'lgan kino kodini kiriting:"
    )
    await callback.answer()


@router.message(KinoStates.delete_code)
async def kino_delete_code(message: Message, state: FSMContext, bot: Bot):
    code = message.text.strip().lower()
    bot_info = await bot.get_me()

    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        bot_id = bot_row['id']

        movie = await conn.fetchrow("""
            SELECT id, name FROM kinobot_movies
            WHERE bot_id = $1 AND code = $2
        """, bot_id, code)

        if not movie:
            await message.answer(
                f"❌ <code>{code}</code> kodi topilmadi.",
                parse_mode="HTML",
                reply_markup=back_admin_kb()
            )
            await state.clear()
            return

        await conn.execute(
            "DELETE FROM kinobot_movies WHERE id = $1", movie['id']
        )

    await state.clear()
    await message.answer(
        f"✅ <b>{movie['name']}</b> o'chirildi.",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


# ── Kinolar ro'yxati ──

@router.callback_query(F.data == "kino_list")
async def kino_list_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin(bot, callback.from_user.id):
        return

    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        movies = await conn.fetch("""
            SELECT code, name FROM kinobot_movies
            WHERE bot_id = $1 ORDER BY added_at DESC
        """, bot_row['id'])

    if not movies:
        await callback.answer("📋 Kinolar yo'q!", show_alert=True)
        return

    lines = [f"<code>{m['code']}</code> — {m['name']}" for m in movies]
    text = f"📋 <b>Kinolar ({len(movies)} ta):</b>\n\n" + "\n".join(lines)

    # Uzun bo'lsa bo'lib yuborish
    if len(text) > 4000:
        text = text[:4000] + "\n\n..."

    await callback.message.edit_text(
        text,
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Statistika ──

@router.callback_query(F.data == "kino_stats")
async def kino_stats_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin(bot, callback.from_user.id):
        return

    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        bot_id = bot_row['id']

        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM kinobot_users WHERE bot_id = $1", bot_id
        )
        total_movies = await conn.fetchval(
            "SELECT COUNT(*) FROM kinobot_movies WHERE bot_id = $1", bot_id
        )
        banned_users = await conn.fetchval("""
            SELECT COUNT(*) FROM kinobot_users
            WHERE bot_id = $1 AND is_banned = TRUE
        """, bot_id)

    await callback.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{total_users}</b>\n"
        f"🎬 Kinolar: <b>{total_movies}</b>\n"
        f"🚫 Banlangan: <b>{banned_users}</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Xabar yuborish ──

@router.callback_query(F.data == "kino_broadcast")
async def kino_broadcast_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin(bot, callback.from_user.id):
        return
    await state.set_state(KinoStates.broadcast_text)
    await callback.message.edit_text(
        "📣 Barcha foydalanuvchilarga yuboriladigan xabarni yozing:"
    )
    await callback.answer()


@router.message(KinoStates.broadcast_text)
async def kino_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    bot_info = await bot.get_me()

    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        users = await conn.fetch("""
            SELECT user_id FROM kinobot_users
            WHERE bot_id = $1 AND is_banned = FALSE
        """, bot_row['id'])

    success, failed = 0, 0
    import asyncio
    for user in users:
        try:
            await bot.send_message(user['user_id'], message.html_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(
        f"✅ Yuborildi: {success}\n❌ Yuborilmadi: {failed}",
        reply_markup=back_admin_kb()
    )


# ── Majburiy kanallar ──

@router.callback_query(F.data == "kino_channels")
async def kino_channels_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin(bot, callback.from_user.id):
        return
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        channels = await conn.fetch(
            "SELECT id, channel_name FROM bot_required_channels WHERE bot_id = $1",
            bot_row['id']
        )
    await callback.message.edit_text(
        f"📢 <b>Majburiy kanallar ({len(channels)} ta)</b>",
        reply_markup=admin_channels_kb([dict(c) for c in channels]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "kino_add_ch")
async def kino_add_ch_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin(bot, callback.from_user.id):
        return
    await state.set_state(KinoStates.add_channel_id)
    await callback.message.edit_text(
        "📢 Kanal ID kiriting:\n<code>@kanal</code> yoki <code>-1001234567890</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(KinoStates.add_channel_id)
async def kino_ch_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text.strip())
    await state.set_state(KinoStates.add_channel_name)
    await message.answer("📝 Kanal nomini kiriting:")


@router.message(KinoStates.add_channel_name)
async def kino_ch_name(message: Message, state: FSMContext):
    await state.update_data(ch_name=message.text.strip())
    await state.set_state(KinoStates.add_channel_url)
    await message.answer("🔗 Kanal URL kiriting:\n<code>https://t.me/kanal</code>", parse_mode="HTML")


@router.message(KinoStates.add_channel_url)
async def kino_ch_url(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        bot_row = await conn.fetchrow(
            "SELECT id FROM bots WHERE bot_username = $1", bot_info.username
        )
        await conn.execute("""
            INSERT INTO bot_required_channels (bot_id, channel_id, channel_name, channel_url)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, bot_row['id'], data['ch_id'], data['ch_name'], message.text.strip())

    await message.answer(
        f"✅ Kanal qo'shildi: <b>{data['ch_name']}</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("kino_del_ch_"))
async def kino_del_ch(callback: CallbackQuery, bot: Bot):
    if not await is_admin(bot, callback.from_user.id):
        return
    ch_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM bot_required_channels WHERE id = $1", ch_id
        )
    await callback.answer("✅ Kanal o'chirildi!", show_alert=True)
    await kino_channels_handler(callback, bot)
