from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp

import database
from database import pool
from keyboards.main_menu import back_to_main_kb, confirm_kb
from keyboards.bot_create_menu import my_bots_kb
from webhook.bot_manager import start_template_bot
from config import WEBHOOK_HOST, TEMPLATE_TYPES

router = Router()

INSTRUCTIONS = {
    "quiz": (
        "🎯 <b>QUIZ BOT — YO'RIQNOMA</b>\n\n"
        "1️⃣ Bot tokeningizni @BotFather dan oling\n"
        "2️⃣ Admin ID ni @userinfobot orqali bilib oling\n\n"
        "📄 <b>Savol fayli (.docx) qoidalari:</b>\n\n"
        "<code>O'zbekiston poytaxti qaysi shahar?\n"
        "A) Samarqand\n"
        "B) Toshkent\n"
        "C) Buxoro\n"
        "D) Namangan\n"
        "=B</code>\n\n"
        "✅ To'g'ri yozish: <code>=B</code>\n"
        "❌ Xato: <code>= B</code> yoki <code>=b</code>\n\n"
        "⚠️ Har savol orasida 1 ta bo'sh qator bo'lsin\n"
        "⚠️ Faqat .docx format qabul qilinadi\n\n"
        "Davom etish uchun bot tokeningizni yuboring 👇"
    ),
    "shop": (
        "🛒 <b>DO'KON BOT — YO'RIQNOMA</b>\n\n"
        "1️⃣ Bot tokeningizni @BotFather dan oling\n"
        "2️⃣ Admin ID ni @userinfobot orqali bilib oling\n\n"
        "📦 <b>Bot imkoniyatlari:</b>\n"
        "• Kategoriyalar va mahsulotlar qo'shish\n"
        "• Rasm, narx va tavsif bilan\n"
        "• Savatcha tizimi\n"
        "• Buyurtmalarni boshqarish\n\n"
        "⚠️ Bot yaratilgandan so'ng admin panel orqali\n"
        "kategoriya va mahsulot qo'shishingiz mumkin\n\n"
        "Davom etish uchun bot tokeningizni yuboring 👇"
    ),
    "broadcaster": (
        "📢 <b>AVTO XABAR BOT — YO'RIQNOMA</b>\n\n"
        "1️⃣ Bot tokeningizni @BotFather dan oling\n"
        "2️⃣ Admin ID ni @userinfobot orqali bilib oling\n\n"
        "📋 <b>Bot imkoniyatlari:</b>\n"
        "• Kanal/guruhga avtomatik xabar\n"
        "• Bir martalik, kunlik, haftalik, oylik rejim\n"
        "• Matn, rasm, video yuborish\n\n"
        "⚠️ MUHIM: Botingizni kanalingizga\n"
        "<b>admin</b> qilib qo'shing!\n"
        "Aks holda xabar yuborilmaydi.\n\n"
        "Davom etish uchun bot tokeningizni yuboring 👇"
    ),
    "referral": (
        "👥 <b>REFERRAL BOT — YO'RIQNOMA</b>\n\n"
        "1️⃣ Bot tokeningizni @BotFather dan oling\n"
        "2️⃣ Admin ID ni @userinfobot orqali bilib oling\n\n"
        "📋 <b>Bot imkoniyatlari:</b>\n"
        "• Referral havola tizimi\n"
        "• Balans va pul yechish\n"
        "• Leaderboard\n"
        "• Ko'p bosqichli referral\n\n"
        "⚠️ Bonus miqdori va pul yechish\n"
        "shartlarini admin paneldan sozlang\n\n"
        "Davom etish uchun bot tokeningizni yuboring 👇"
    ),
    "kinobot": (
        "🎬 <b>KINO BOT — YO'RIQNOMA</b>\n\n"
        "1️⃣ Bot tokeningizni @BotFather dan oling\n"
        "2️⃣ Admin ID ni @userinfobot orqali bilib oling\n\n"
        "📋 <b>Bot ishlash tartibi:</b>\n"
        "• Admin kino qo'shadi (kod + nom + fayl)\n"
        "• Kanalingizda kino kodini e'lon qiling\n"
        "• Foydalanuvchi kodni yozsa fayl yuboriladi\n\n"
        "⚠️ Kod qisqa va yodda qolsin\n"
        "Masalan: <code>001</code>, <code>batman</code>\n\n"
        "Davom etish uchun bot tokeningizni yuboring 👇"
    ),
}

class BotCreateStates(StatesGroup):
    waiting_token = State()
    waiting_admin_id = State()
    confirm = State()

# ═══════════════════════════════════════
# ASOSIY MENYU TUGMASI (KAFOLATLANGAN HANDLER)
# ═══════════════════════════════════════
# Agar start.py ichida bu tugma yozilmagan bo'lsa, shu handler ishlaydi. 
# Bu yerda shablonlar inline tugmasini chiqaruvchi keyboardingizni (masalan, templates_kb) ulashingiz kerak.
@router.message(F.text == "🆕 Bot yaratish")
async def main_menu_create_bot(message: Message, state: FSMContext):
    await state.clear()
    # 💡 Bu yerda shablonlar inline tugmalari chiqishi kerak. 
    # Hozircha namunaviy matn, o'zingizning inline keyboard funksiyangizni reply_markup'ga qo'ying:
    from keyboards.main_menu import template_select_kb
await message.answer("🤖 Yaratgingiz kelgan bot shablonini tanlang:", reply_markup=template_select_kb())

# ═══════════════════════════════════════
# SHABLON TANLASH → YO'RIQNOMA
# ═══════════════════════════════════════
@router.callback_query(F.data.startswith("template_"))
async def template_selected(callback: CallbackQuery, state: FSMContext):
    template_type = callback.data.replace("template_", "")

    if template_type not in TEMPLATE_TYPES:
        await callback.answer("❌ Noma'lum shablon!", show_alert=True)
        return

    await state.set_state(BotCreateStates.waiting_token)
    await state.update_data(template_type=template_type)

    instruction = INSTRUCTIONS.get(template_type, "")
    await callback.message.edit_text(
        instruction,
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

# ═══════════════════════════════════════
# TOKEN QABUL QILISH
# ═══════════════════════════════════════
@router.message(BotCreateStates.waiting_token)
async def token_received(message: Message, state: FSMContext):
    token = message.text.strip()

    if ":" not in token or len(token) < 30:
        await message.answer(
            "❌ <b>Noto'g'ri token formati!</b>\n\n"
            "Token shu ko'rinishda bo'lishi kerak:\n"
            "<code>1234567890:ABCdefGHIjklMNOpqrsTUVwxyz</code>\n\n"
            "Tokenni @BotFather dan oling va qayta yuboring.",
            parse_mode="HTML"
        )
        return

    async with database.pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM bots WHERE bot_token = $1", token
        )
    if exists:
        await message.answer(
            "❌ Bu token allaqachon ishlatilgan!\n"
            "Boshqa bot tokeni yuboring.",
        )
        return

    await message.answer("⏳ Token tekshirilmoqda...")
    bot_info = await verify_token(token)

    if not bot_info:
        await message.answer(
            "❌ <b>Token yaroqsiz!</b>\n\n"
            "Tokenni @BotFather dan to'g'ri nusxalab yuboring.",
            parse_mode="HTML"
        )
        return

    await state.update_data(
        bot_token=token,
        bot_username=bot_info.get("username", ""),
        bot_name=bot_info.get("first_name", "")
    )
    await state.set_state(BotCreateStates.waiting_admin_id)

    await message.answer(
        f"✅ <b>Bot topildi:</b> @{bot_info.get('username')}\n\n"
        f"Endi <b>Admin ID</b> ni yuboring.\n\n"
        f"💡 ID ni bilish uchun @userinfobot ga /start yozing.",
        parse_mode="HTML"
    )

async def verify_token(token: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return data["result"]
                return None
    except Exception:
        return None

# ═══════════════════════════════════════
# ADMIN ID QABUL QILISH
# ═══════════════════════════════════════
@router.message(BotCreateStates.waiting_admin_id)
async def admin_id_received(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Admin ID faqat raqam bo'lishi kerak!\n\n"
            "Masalan: <code>987654321</code>\n\n"
            "ID ni bilish uchun @userinfobot ga /start yozing.",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    await state.update_data(admin_id=admin_id)
    await state.set_state(BotCreateStates.confirm)

    template_name = TEMPLATE_TYPES.get(data['template_type'], "Noma'lum")

    await message.answer(
        f"📋 <b>Tasdiqlang:</b>\n\n"
        f"📦 Shablon: {template_name}\n"
        f"🤖 Bot: @{data['bot_username']}\n"
        f"👤 Admin ID: <code>{admin_id}</code>\n\n"
        f"Ma'lumotlar to'g'rimi?",
        reply_markup=confirm_kb(
            confirm_data="bot_create_confirm",
            cancel_data="main_menu"
        ),
        parse_mode="HTML"
    )

# ═══════════════════════════════════════
# TASDIQLASH VA BOT YARATISH (STATE QO'SHILDI)
# ═══════════════════════════════════════
#  BotCreateStates.confirm cheklovi qo'shildi! Endi tugma 100% ishlaydi.
@router.callback_query(F.data == "bot_create_confirm", BotCreateStates.confirm)
async def bot_create_confirmed(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id

    await callback.message.edit_text("⏳ Bot yaratilmoqda...")

    async with database.pool.acquire() as conn:
        bot_id = await conn.fetchval("""
            INSERT INTO bots (user_id, bot_token, bot_username, admin_id, template_type, is_running)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            RETURNING id
        """,
            user_id,
            data['bot_token'],
            data['bot_username'],
            data['admin_id'],
            data['template_type']
        )

        await create_template_settings(conn, bot_id, data['template_type'])

    await state.clear()

    bot_data = {
        'id': bot_id,
        'bot_token': data['bot_token'],
        'bot_username': data['bot_username'],
        'admin_id': data['admin_id'],
        'template_type': data['template_type'],
        'is_running': True,
    }
    await start_template_bot(bot_data)

    template_name = TEMPLATE_TYPES.get(data['template_type'], "")

    await callback.message.edit_text(
        f"🎉 <b>Bot muvaffaqiyatli yaratildi!</b>\n\n"
        f"📦 Shablon: {template_name}\n"
        f"🤖 Bot: @{data['bot_username']}\n\n"
        f"✅ Bot hozir ishlayapti!\n\n"
        f"💡 «Mening botlarim» dan botingizni boshqarishingiz mumkin.",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

async def create_template_settings(conn, bot_id: int, template_type: str):
    if template_type == "quiz":
        await conn.execute("""
            INSERT INTO quiz_settings (bot_id, questions_count, time_per_question)
            VALUES ($1, 10, 30)
            ON CONFLICT DO NOTHING
        """, bot_id)

    elif template_type == "referral":
        await conn.execute("""
            INSERT INTO referral_bot_settings (bot_id, bonus_per_referral, min_withdrawal)
            VALUES ($1, 1000, 10000)
            ON CONFLICT DO NOTHING
        """, bot_id)
