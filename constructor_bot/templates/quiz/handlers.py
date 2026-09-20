from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
import random
import os

import database
from database import pool
from templates.quiz.keyboards import (
    subscription_kb, start_quiz_kb, answer_kb,
    result_kb, admin_main_kb, back_admin_kb,
    users_list_kb, user_action_kb
)
from templates.quiz.utils import parse_quiz_file

router = Router()


class QuizStates(StatesGroup):
    in_test = State()
    # Admin
    upload_file = State()
    set_count = State()
    set_time = State()
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
            "SELECT * FROM quiz_settings WHERE bot_id = $1", bot_id
        )
        return dict(row) if row else {"questions_count": 10, "time_per_question": 30}


async def is_admin_user(bot: Bot, user_id: int) -> bool:
    row = await get_bot_row(bot)
    return row and row['admin_id'] == user_id


async def is_banned_user(bot_id: int, user_id: int) -> bool:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 1 FROM quiz_banned_users
            WHERE bot_id = $1 AND user_id = $2
        """, bot_id, user_id)
        return bool(row)


# ═══════════════════════════════════════
# FOYDALANUVCHI
# ═══════════════════════════════════════

@router.message(CommandStart())
async def quiz_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    row = await get_bot_row(bot)
    if not row:
        return
    bot_id = row['id']
    user_id = message.from_user.id

    if await is_banned_user(bot_id, user_id):
        await message.answer("🚫 Siz bloklangansiz.")
        return

    ok, not_sub = await check_sub(bot, user_id, bot_id)
    if not ok:
        await message.answer(
            "📢 Botdan foydalanish uchun obuna bo'ling:",
            reply_markup=subscription_kb(not_sub)
        )
        return

    settings = await get_settings(bot_id)
    is_admin = await is_admin_user(bot, user_id)
    await message.answer(
        f"🎯 <b>Quiz Bot</b>\n\n"
        f"📝 Savollar soni: <b>{settings['questions_count']} ta</b>\n"
        f"⏱ Har savolga vaqt: <b>{settings['time_per_question']} soniya</b>\n\n"
        f"Testni boshlashga tayyormisiz?",
        reply_markup=start_quiz_kb(is_admin),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "quiz_check_sub")
async def quiz_check_sub(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return
    ok, not_sub = await check_sub(bot, callback.from_user.id, row['id'])
    if not ok:
        await callback.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    await callback.answer("✅ Obuna tasdiqlandi!")
    settings = await get_settings(row['id'])
    is_admin = await is_admin_user(bot, callback.from_user.id)
    await callback.message.edit_text(
        f"🎯 <b>Quiz Bot</b>\n\n"
        f"📝 Savollar soni: <b>{settings['questions_count']} ta</b>\n"
        f"⏱ Har savolga vaqt: <b>{settings['time_per_question']} soniya</b>\n\n"
        f"Testni boshlashga tayyormisiz?",
        reply_markup=start_quiz_kb(is_admin),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "quiz_start")
async def quiz_start_test(callback: CallbackQuery, bot: Bot, state: FSMContext):
    row = await get_bot_row(bot)
    if not row:
        return
    bot_id = row['id']
    user_id = callback.from_user.id

    if await is_banned_user(bot_id, user_id):
        await callback.answer("🚫 Siz bloklangansiz!", show_alert=True)
        return

    ok, not_sub = await check_sub(bot, user_id, bot_id)
    if not ok:
        await callback.answer("❌ Avval obuna bo'ling!", show_alert=True)
        return

    settings = await get_settings(bot_id)

    async with database.pool.acquire() as conn:
        all_questions = await conn.fetch(
            "SELECT * FROM quiz_questions WHERE bot_id = $1", bot_id
        )

    if not all_questions:
        await callback.answer("❌ Hali savollar yuklanmagan!", show_alert=True)
        return

    count = min(settings['questions_count'], len(all_questions))
    selected = random.sample([dict(q) for q in all_questions], count)

    await state.set_state(QuizStates.in_test)
    await state.update_data(
        questions=selected,
        current=0,
        score=0,
        bot_id=bot_id,
        time_per_q=settings['time_per_question'],
        msg_id=None,
    )

    await callback.message.edit_text("🎯 Test boshlanmoqda...")
    await send_question(callback.message, state, bot, user_id)
    await callback.answer()


async def send_question(message: Message, state: FSMContext, bot: Bot, user_id: int):
    data = await state.get_data()
    questions = data['questions']
    current = data['current']
    time_limit = data['time_per_q']

    if current >= len(questions):
        await finish_test(message, state, bot, user_id)
        return

    q = questions[current]
    text = (
        f"❓ <b>Savol {current + 1}/{len(questions)}</b>\n\n"
        f"{q['question']}\n\n"
        f"🅐 {q['option_a']}\n"
        f"🅑 {q['option_b']}\n"
        f"🅒 {q['option_c']}\n"
        f"🅓 {q['option_d']}\n\n"
        f"⏱ Vaqt: <b>{time_limit} soniya</b>"
    )

    sent = await bot.send_message(
        user_id,
        text,
        reply_markup=answer_kb(current),
        parse_mode="HTML"
    )
    await state.update_data(msg_id=sent.message_id)

    # Vaqt tugashi
    await asyncio.sleep(time_limit)

    # Hali javob bermadimi?
    current_data = await state.get_data()
    if current_data.get('current') == current:
        try:
            await bot.edit_message_text(
                text + "\n\n⏰ <b>Vaqt tugadi!</b>",
                chat_id=user_id,
                message_id=sent.message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass
        await state.update_data(current=current + 1)
        await send_question(message, state, bot, user_id)


@router.callback_query(F.data.startswith("quiz_ans_"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split("_")
    q_index = int(parts[2])
    answer = parts[3]

    data = await state.get_data()

    if data.get('current') != q_index:
        await callback.answer("⏰ Vaqt o'tdi!", show_alert=True)
        return

    question = data['questions'][q_index]
    correct = question['correct_answer']
    score = data['score']

    if answer == correct:
        score += 1
        result_text = "✅ To'g'ri!"
    else:
        result_text = f"❌ Noto'g'ri! To'g'ri javob: <b>{correct}</b>"

    await state.update_data(score=score, current=q_index + 1)

    try:
        await callback.message.edit_text(
            callback.message.text + f"\n\n{result_text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer(result_text.replace("<b>", "").replace("</b>", ""), show_alert=False)

    await asyncio.sleep(1)
    await send_question(callback.message, state, bot, callback.from_user.id)


async def finish_test(message: Message, state: FSMContext, bot: Bot, user_id: int):
    data = await state.get_data()
    score = data['score']
    total = len(data['questions'])
    bot_id = data['bot_id']

    percent = (score / total) * 100 if total > 0 else 0

    if percent >= 80:
        grade = "🥇 A'lo!"
    elif percent >= 60:
        grade = "🥈 Yaxshi"
    elif percent >= 40:
        grade = "🥉 Qoniqarli"
    else:
        grade = "❌ Qoniqarsiz"

    user = await bot.get_chat(user_id)

    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO quiz_results (bot_id, user_id, username, full_name, score, total)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, bot_id, user_id, user.username, user.full_name, score, total)

        admin_id = await conn.fetchval(
            "SELECT admin_id FROM bots WHERE id = $1", bot_id
        )

    await state.clear()

    result_text = (
        f"🏁 <b>Test yakunlandi!</b>\n\n"
        f"✅ To'g'ri javoblar: <b>{score}/{total}</b>\n"
        f"📊 Foiz: <b>{percent:.0f}%</b>\n"
        f"🏅 Baho: {grade}"
    )

    await bot.send_message(
        user_id,
        result_text,
        reply_markup=result_kb(),
        parse_mode="HTML"
    )

    # Adminga ham yuborish
    try:
        await bot.send_message(
            admin_id,
            f"📊 <b>Yangi natija</b>\n\n"
            f"👤 {user.full_name} (@{user.username or 'yo\'q'})\n"
            f"✅ {score}/{total} — {percent:.0f}%\n{grade}",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "quiz_leaderboard")
async def quiz_leaderboard(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return

    async with database.pool.acquire() as conn:
        top = await conn.fetch("""
            SELECT full_name, username, score, total,
                   ROUND(score::numeric/total*100) as percent
            FROM quiz_results
            WHERE bot_id = $1
            ORDER BY percent DESC, score DESC
            LIMIT 10
        """, row['id'])

    if not top:
        await callback.answer("🏆 Hali natijalar yo'q!", show_alert=True)
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = []
    for i, r in enumerate(top):
        name = r['full_name'] or f"@{r['username']}" or "Anonim"
        lines.append(f"{medals[i]} {name} — {r['score']}/{r['total']} ({r['percent']}%)")

    await callback.message.edit_text(
        "🏆 <b>Leaderboard (Top 10)</b>\n\n" + "\n".join(lines),
        reply_markup=start_quiz_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════

@router.message(Command("admin"))
async def quiz_admin(message: Message, bot: Bot):
    if not await is_admin_user(bot, message.from_user.id):
        return
    await message.answer("👨‍💼 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "quiz_admin")
async def quiz_admin_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("👨‍💼 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")
    await callback.answer()


# ── Fayl yuklash ──

@router.callback_query(F.data == "quiz_upload")
async def quiz_upload_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(QuizStates.upload_file)
    await callback.message.edit_text(
        "📄 <b>Savollar faylini yuboring (.docx)</b>\n\n"
        "Fayl formati:\n"
        "<code>Savol matni\n"
        "A) variant\nB) variant\nC) variant\nD) variant\n=B</code>\n\n"
        "Har savol orasida bo'sh qator bo'lsin.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(QuizStates.upload_file, F.document)
async def quiz_file_received(message: Message, state: FSMContext, bot: Bot):
    if not message.document.file_name.endswith('.docx'):
        await message.answer("❌ Faqat .docx fayl yuborilsin!")
        return

    row = await get_bot_row(bot)
    bot_id = row['id']

    await message.answer("⏳ Fayl o'qilmoqda...")

    # Faylni yuklab olish
    file = await bot.get_file(message.document.file_id)
    file_path = f"/tmp/quiz_{bot_id}.docx"
    await bot.download_file(file.file_path, file_path)

    try:
        questions = parse_quiz_file(file_path)
    except Exception as e:
        await message.answer(f"❌ Faylni o'qishda xato: {e}", reply_markup=back_admin_kb())
        return
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    if not questions:
        await message.answer(
            "❌ Savollar topilmadi! Fayl formatini tekshiring.",
            reply_markup=back_admin_kb()
        )
        await state.clear()
        return

    async with database.pool.acquire() as conn:
        # Eski savollarni o'chirish
        await conn.execute("DELETE FROM quiz_questions WHERE bot_id = $1", bot_id)

        # Yangi savollarni yozish
        for q in questions:
            await conn.execute("""
                INSERT INTO quiz_questions
                (bot_id, question, option_a, option_b, option_c, option_d, correct_answer)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, bot_id, q['question'], q['a'], q['b'], q['c'], q['d'], q['answer'])

    await state.clear()
    await message.answer(
        f"✅ <b>{len(questions)} ta savol yuklandi!</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.message(QuizStates.upload_file)
async def quiz_file_wrong(message: Message):
    await message.answer("❌ Iltimos, .docx fayl yuboring.")


# ── Sozlamalar ──

@router.callback_query(F.data == "quiz_settings")
async def quiz_settings_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    settings = await get_settings(row['id'])

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Savollar soni", callback_data="quiz_set_count")],
        [InlineKeyboardButton(text="⏱ Har savolga vaqt", callback_data="quiz_set_time")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz_admin")],
    ])

    await callback.message.edit_text(
        f"⚙️ <b>Test sozlamalari</b>\n\n"
        f"📝 Savollar soni: <b>{settings['questions_count']} ta</b>\n"
        f"⏱ Har savolga vaqt: <b>{settings['time_per_question']} soniya</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "quiz_set_count")
async def quiz_set_count_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(QuizStates.set_count)
    await callback.message.edit_text("📝 Nechta savol yuborilsin? (raqam kiriting):")
    await callback.answer()


@router.message(QuizStates.set_count)
async def quiz_set_count(message: Message, state: FSMContext, bot: Bot):
    try:
        count = int(message.text.strip())
        if count < 1 or count > 200:
            raise ValueError
    except ValueError:
        await message.answer("❌ 1 dan 200 gacha raqam kiriting.")
        return

    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE quiz_settings SET questions_count = $1 WHERE bot_id = $2
        """, count, row['id'])

    await state.clear()
    await message.answer(
        f"✅ Savollar soni <b>{count} ta</b> ga o'zgartirildi.",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "quiz_set_time")
async def quiz_set_time_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(QuizStates.set_time)
    await callback.message.edit_text("⏱ Har savolga necha soniya? (raqam kiriting):")
    await callback.answer()


@router.message(QuizStates.set_time)
async def quiz_set_time(message: Message, state: FSMContext, bot: Bot):
    try:
        seconds = int(message.text.strip())
        if seconds < 5 or seconds > 300:
            raise ValueError
    except ValueError:
        await message.answer("❌ 5 dan 300 gacha soniya kiriting.")
        return

    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE quiz_settings SET time_per_question = $1 WHERE bot_id = $2
        """, seconds, row['id'])

    await state.clear()
    await message.answer(
        f"✅ Vaqt <b>{seconds} soniya</b> ga o'zgartirildi.",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


# ── Foydalanuvchilar ──

@router.callback_query(F.data == "quiz_users")
async def quiz_users_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT DISTINCT qr.user_id, qr.full_name, qr.username,
                COALESCE(qb.user_id IS NOT NULL, FALSE) as is_banned
            FROM quiz_results qr
            LEFT JOIN quiz_banned_users qb
                ON qr.bot_id = qb.bot_id AND qr.user_id = qb.user_id
            WHERE qr.bot_id = $1
            LIMIT 50
        """, row['id'])

    if not users:
        await callback.answer("👥 Hali foydalanuvchilar yo'q!", show_alert=True)
        return

    await callback.message.edit_text(
        f"👥 <b>Foydalanuvchilar</b>",
        reply_markup=users_list_kb([dict(u) for u in users], row['id']),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quiz_ban_"))
async def quiz_ban_user(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO quiz_banned_users (bot_id, user_id)
            VALUES ($1, $2) ON CONFLICT DO NOTHING
        """, row['id'], user_id)

    await callback.answer("🚫 Banlandi!", show_alert=True)


@router.callback_query(F.data.startswith("quiz_unban_"))
async def quiz_unban_user(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM quiz_banned_users WHERE bot_id = $1 AND user_id = $2
        """, row['id'], user_id)

    await callback.answer("✅ Ban olib tashlandi!", show_alert=True)


# ── Natijalar ──

@router.callback_query(F.data == "quiz_results")
async def quiz_results_handler(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        results = await conn.fetch("""
            SELECT full_name, username, score, total,
                   ROUND(score::numeric/total*100) as percent,
                   completed_at
            FROM quiz_results WHERE bot_id = $1
            ORDER BY completed_at DESC LIMIT 20
        """, row['id'])

    if not results:
        await callback.answer("📊 Hali natijalar yo'q!", show_alert=True)
        return

    lines = []
    for r in results:
        name = r['full_name'] or f"@{r['username']}"
        date = r['completed_at'].strftime('%d.%m')
        lines.append(f"👤 {name} — {r['score']}/{r['total']} ({r['percent']}%) {date}")

    await callback.message.edit_text(
        "📊 <b>So'nggi natijalar:</b>\n\n" + "\n".join(lines),
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Xabar yuborish ──

@router.callback_query(F.data == "quiz_broadcast")
async def quiz_broadcast_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(QuizStates.broadcast_text)
    await callback.message.edit_text("📣 Barcha foydalanuvchilarga xabar yozing:")
    await callback.answer()


@router.message(QuizStates.broadcast_text)
async def quiz_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT DISTINCT user_id FROM quiz_results WHERE bot_id = $1
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

@router.callback_query(F.data == "quiz_channels")
async def quiz_channels_handler(callback: CallbackQuery, bot: Bot):
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
            callback_data=f"quiz_del_ch_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Qo'shish", callback_data="quiz_add_ch")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz_admin")])

    await callback.message.edit_text(
        f"📢 Majburiy kanallar ({len(channels)} ta)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "quiz_add_ch")
async def quiz_add_ch(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(QuizStates.add_channel_id)
    await callback.message.edit_text("📢 Kanal ID kiriting:")
    await callback.answer()


@router.message(QuizStates.add_channel_id)
async def quiz_ch_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text.strip())
    await state.set_state(QuizStates.add_channel_name)
    await message.answer("📝 Kanal nomini kiriting:")


@router.message(QuizStates.add_channel_name)
async def quiz_ch_name(message: Message, state: FSMContext):
    await state.update_data(ch_name=message.text.strip())
    await state.set_state(QuizStates.add_channel_url)
    await message.answer("🔗 Kanal URL kiriting:")


@router.message(QuizStates.add_channel_url)
async def quiz_ch_url(message: Message, state: FSMContext, bot: Bot):
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


@router.callback_query(F.data.startswith("quiz_del_ch_"))
async def quiz_del_ch(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    ch_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM bot_required_channels WHERE id = $1", ch_id)
    await callback.answer("✅ O'chirildi!", show_alert=True)
    await quiz_channels_handler(callback, bot)
