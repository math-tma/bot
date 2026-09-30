import logging

import aiohttp
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatAction

import database
from templates.ai_agent.keyboards import (
    admin_main_kb, back_admin_kb, model_select_kb, clear_history_confirm_kb
)

router = Router()
logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL_NAMES = {
    "gemini-2.0-flash": "⚡ Flash (tez)",
    "gemini-1.5-pro": "⚖️ Pro (muvozanatli)",
    "gemini-1.5-flash": "💫 Flash 1.5 (arzon)",
}


class AiAgentStates(StatesGroup):
    waiting_prompt = State()
    waiting_apikey = State()


# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════

async def get_bot_row(bot: Bot) -> dict | None:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_token = $1", bot.token
        )
        return dict(row) if row else None


async def is_admin_user(bot: Bot, user_id: int) -> bool:
    row = await get_bot_row(bot)
    return bool(row and row['admin_id'] == user_id)


async def get_settings(bot_id: int) -> dict | None:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ai_agent_settings WHERE bot_id = $1", bot_id
        )
        return dict(row) if row else None


async def call_gemini(api_key: str, model: str, system_prompt: str, messages: list) -> str:
    """
    Google Gemini API'ga so'rov yuboradi va matnli javobni qaytaradi.
    Xato bo'lsa, tushunarli xabar bilan Exception ko'taradi.
    """
    # Gemini API formatiga o'girish: eski formatni yangi formatga
    gemini_messages = []
    
    # System prompt'ni birinchi user xabari sifatida qo'shish
    if system_prompt:
        gemini_messages.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[END SYSTEM]\n\nShunga amal qil."}]
        })
        gemini_messages.append({
            "role": "model",
            "parts": [{"text": "Tushundim. Sizning ko'rsatmalaringiz asosida javob beraman."}]
        })
    
    # Suhbat tarixini qo'shish
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        gemini_messages.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    headers = {
        "Content-Type": "application/json",
    }
    
    payload = {
        "contents": gemini_messages,
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature": 0.7,
        }
    }
    
    url = f"{GEMINI_URL.format(model=model)}?key={api_key}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, headers=headers, json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            data = await resp.json()

            if resp.status != 200:
                error_msg = data.get("error", {}).get("message", "Noma'lum xato")

                if resp.status == 401 or "API key" in error_msg:
                    raise ValueError("API kalit yaroqsiz yoki eskirgan")
                elif resp.status == 429:
                    raise ValueError("So'rovlar chegarasiga yetildi (rate limit) — bir oz kutib qayta urinib ko'ring")
                elif resp.status == 400 and "quota" in error_msg.lower():
                    raise ValueError("Hisobingizda balans yetarli emas (Google Cloud Console'da to'ldiring)")
                elif resp.status == 400 and ("blocked" in error_msg.lower() or "safety" in error_msg.lower()):
                    raise ValueError("Javob xavfsizlik sababli bloklandi. Boshqa savol bering.")
                else:
                    raise ValueError(f"Xato: {error_msg}")

            # Gemini API javobidan matnni chiqarish
            try:
                candidates = data.get("candidates", [])
                if not candidates:
                    return "Javob olib bo'lmadi. Qayta urinib ko'ring."
                
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                
                if not parts:
                    return "Javob olib bo'lmadi. Qayta urinib ko'ring."
                
                text = parts[0].get("text", "...").strip()
                return text if text else "..."
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Gemini javobini parse qilishda xato: {e}, data: {data}")
                return "Javobni to'liq olib bo'lmadi."


async def get_conversation_history(bot_id: int, user_id: int, limit: int) -> list:
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content FROM ai_agent_messages
            WHERE bot_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """, bot_id, user_id, limit)
        rows = list(reversed(rows))
        return [{"role": r['role'], "content": r['content']} for r in rows]


async def save_message(bot_id: int, user_id: int, role: str, content: str):
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_agent_messages (bot_id, user_id, role, content)
            VALUES ($1, $2, $3, $4)
        """, bot_id, user_id, role, content)


# ═══════════════════════════════════════
# FOYDALANUVCHI — /start
# ═══════════════════════════════════════

@router.message(CommandStart())
async def ai_start(message: Message, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return

    settings = await get_settings(row['id'])
    is_admin = row['admin_id'] == message.from_user.id

    if not settings:
        if is_admin:
            await message.answer(
                "👋 <b>AI Agent botga xush kelibsiz!</b>\n\n"
                "⚠️ Bot hali sozlanmagan. Sozlash uchun /admin buyrug'ini yuboring — "
                "avval Google Gemini API kalitingizni, keyin bot qanday javob berishi "
                "kerakligini (system prompt) kiritasiz.",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "⚠️ Bot hali sozlanmagan. Iltimos keyinroq urinib ko'ring."
            )
        return

    text = "👋 <b>Salom!</b>\n\nSavolingizni yozing, javob beraman."
    if is_admin:
        text += "\n\n👨‍💻 Sozlamalar uchun /admin buyrug'ini yuboring."

    await message.answer(text, parse_mode="HTML")


# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════

@router.message(Command("admin"))
async def ai_admin_cmd(message: Message, bot: Bot):
    if not await is_admin_user(bot, message.from_user.id):
        return
    await message.answer("👨‍💼 <b>AI Agent — Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "ai_admin")
async def ai_admin_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("👨‍💼 <b>AI Agent — Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")
    await callback.answer()


# ── SYSTEM PROMPT ──

@router.callback_query(F.data == "ai_prompt")
async def ai_prompt_view(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    settings = await get_settings(row['id'])
    current = settings['system_prompt'] if settings else "(hali kiritilmagan)"

    await state.set_state(AiAgentStates.waiting_prompt)
    await callback.message.edit_text(
        f"📝 <b>Joriy system prompt:</b>\n\n<code>{current}</code>\n\n"
        f"Yangi system promptni yozib yuboring "
        f"(bu bot qanday xarakterda, qanday tilda, qaysi mavzularda "
        f"javob berishini belgilaydi):",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AiAgentStates.waiting_prompt)
async def ai_prompt_received(message: Message, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, message.from_user.id):
        return
    row = await get_bot_row(bot)
    new_prompt = message.text.strip()

    async with database.pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT bot_id FROM ai_agent_settings WHERE bot_id = $1", row['id']
        )
        if exists:
            await conn.execute(
                "UPDATE ai_agent_settings SET system_prompt = $1 WHERE bot_id = $2",
                new_prompt, row['id']
            )
            await state.clear()
            await message.answer("✅ System prompt yangilandi!", reply_markup=admin_main_kb())
        else:
            await state.update_data(system_prompt=new_prompt)
            await state.set_state(AiAgentStates.waiting_apikey)
            await message.answer(
                "✅ Qabul qilindi!\n\n"
                "🔑 Endi Google Gemini API kalitingizni yuboring.\n\n"
                "💡 Kalitni <a href='https://ai.google.dev/'>ai.google.dev</a> dan olishingiz mumkin — "
                "<b>Get API Key</b> tugmasini bosing va bepul kalit oling.",
                parse_mode="HTML",
                disable_web_page_preview=True
            )


# ── API KALIT ──

@router.callback_query(F.data == "ai_apikey")
async def ai_apikey_view(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    settings = await get_settings(row['id'])
    masked = "(hali kiritilmagan)"
    if settings and settings.get('api_key'):
        k = settings['api_key']
        masked = f"{k[:10]}...{k[-4:]}" if len(k) > 14 else "***"

    await state.set_state(AiAgentStates.waiting_apikey)
    await callback.message.edit_text(
        f"🔑 <b>Joriy API kalit:</b> <code>{masked}</code>\n\n"
        f"Yangi Google Gemini API kalitni yuboring "
        f"(<a href='https://ai.google.dev/'>ai.google.dev</a> dan olinadi):",
        reply_markup=back_admin_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.message(AiAgentStates.waiting_apikey)
async def ai_apikey_received(message: Message, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, message.from_user.id):
        return

    api_key = message.text.strip()
    # Xavfsizlik: kalitni chatdan darhol o'chiramiz
    try:
        await message.delete()
    except Exception:
        pass

    if len(api_key) < 20:
        await message.answer(
            "❌ Bu Gemini API kaliti ko'rinishiga o'xshamayapti. "
            "Kalitni <a href='https://ai.google.dev/'>ai.google.dev</a> dan oling va qayta yuboring.",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return

    status_msg = await message.answer("⏳ Kalit tekshirilmoqda...")

    # Kalitni tekshirish — juda qisqa test so'rovi bilan
    try:
        await call_gemini(api_key, "gemini-1.5-flash", "test", [{"role": "user", "content": "Hi"}])
    except ValueError as e:
        await status_msg.edit_text(f"❌ Kalit ishlamadi: {e}\n\nQayta yuboring:")
        return
    except Exception as e:
        logger.error(f"API kalit tekshirishda kutilmagan xato: {e}")
        await status_msg.edit_text("❌ Kalitni tekshirib bo'lmadi. Qayta urinib ko'ring.")
        return

    row = await get_bot_row(bot)
    data = await state.get_data()
    system_prompt = data.get('system_prompt')

    async with database.pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT bot_id FROM ai_agent_settings WHERE bot_id = $1", row['id']
        )
        if exists:
            await conn.execute(
                "UPDATE ai_agent_settings SET api_key = $1 WHERE bot_id = $2",
                api_key, row['id']
            )
        else:
            await conn.execute("""
                INSERT INTO ai_agent_settings (bot_id, api_key, system_prompt)
                VALUES ($1, $2, $3)
            """, row['id'], api_key, system_prompt or "Siz foydali AI yordamchisiz.")

    await state.clear()
    await status_msg.edit_text(
        "✅ <b>Kalit tasdiqlandi va saqlandi!</b>\n\nBot ishga tayyor 🎉",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )


# ── MODEL TANLASH ──

@router.callback_query(F.data == "ai_model")
async def ai_model_view(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    settings = await get_settings(row['id'])
    current = MODEL_NAMES.get(settings['model'], settings['model']) if settings else "—"

    await callback.message.edit_text(
        f"🧠 <b>Joriy model:</b> {current}\n\n"
        f"⚡ Flash — eng tez va arzon, oddiy suhbat uchun\n"
        f"⚖️ Pro — kuchli, murakkab vazifalar uchun mos\n"
        f"💫 Flash 1.5 — eng yangi, tez va arzon (tavsiyalangan)\n\n"
        f"Tanlang:",
        reply_markup=model_select_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_setmodel_"))
async def ai_model_set(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    model = callback.data.replace("ai_setmodel_", "")
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        await conn.execute(
            "UPDATE ai_agent_settings SET model = $1 WHERE bot_id = $2",
            model, row['id']
        )

    await callback.answer(f"✅ Model {MODEL_NAMES.get(model, model)} qilib o'rnatildi!", show_alert=True)
    await callback.message.edit_text("👨‍💼 <b>AI Agent — Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


# ── SUHBAT TARIXINI TOZALASH ──

@router.callback_query(F.data == "ai_clear_history")
async def ai_clear_history_ask(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await callback.message.edit_text(
        "🗑 <b>Diqqat!</b> Barcha foydalanuvchilar bilan suhbat tarixi "
        "butunlay o'chiriladi. Bu amalni qaytarib bo'lmaydi.\n\n"
        "Davom etasizmi?",
        reply_markup=clear_history_confirm_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ai_clear_history_confirm")
async def ai_clear_history_confirm(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM ai_agent_messages WHERE bot_id = $1", row['id'])

    await callback.answer("✅ Suhbat tarixi tozalandi!", show_alert=True)
    await callback.message.edit_text("👨‍💼 <b>AI Agent — Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


# ── STATISTIKA ──

@router.callback_query(F.data == "ai_stats")
async def ai_stats_view(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        total_messages = await conn.fetchval(
            "SELECT COUNT(*) FROM ai_agent_messages WHERE bot_id = $1", row['id']
        )
        unique_users = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM ai_agent_messages WHERE bot_id = $1", row['id']
        )

    from utils.usage import get_today_request_count, get_bot_current_tier
    today_requests = await get_today_request_count(row['id'])
    tier = await get_bot_current_tier(row['id'])

    await callback.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"💬 Jami xabarlar: <b>{total_messages:,}</b>\n"
        f"👥 Noyob foydalanuvchilar: <b>{unique_users:,}</b>\n"
        f"📈 Bugungi so'rovlar: <b>{today_requests:,}</b>\n"
        f"💎 Joriy tarif: <b>{tier['tier_name']}</b> ({tier['daily_price']:,} so'm/kun)",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# ASOSIY SUHBAT (oddiy xabarlar)
# ═══════════════════════════════════════

@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def ai_chat(message: Message, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return

    settings = await get_settings(row['id'])
    if not settings or not settings.get('api_key'):
        if row['admin_id'] == message.from_user.id:
            await message.answer(
                "⚠️ Bot hali to'liq sozlanmagan. /admin orqali sozlang."
            )
        else:
            await message.answer("⚠️ Bot hali sozlanmoqda, birozdan so'ng urinib ko'ring.")
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    history = await get_conversation_history(
        row['id'], message.from_user.id, settings.get('max_history', 10)
    )
    history.append({"role": "user", "content": message.text})

    try:
        reply = await call_gemini(
            settings['api_key'], settings.get('model', 'gemini-1.5-flash'),
            settings['system_prompt'], history
        )
    except ValueError as e:
        error_text = str(e)
        if row['admin_id'] == message.from_user.id:
            await message.answer(f"❌ Xato: {error_text}\n\n/admin orqali sozlamalarni tekshiring.")
        else:
            await message.answer("⚠️ Hozircha javob bera olmayapman, birozdan so'ng qayta urinib ko'ring.")
        logger.warning(f"AI agent xatosi (bot_id={row['id']}): {error_text}")
        return
    except Exception as e:
        logger.error(f"AI agent kutilmagan xato (bot_id={row['id']}): {e}")
        await message.answer("⚠️ Xatolik yuz berdi, birozdan so'ng qayta urinib ko'ring.")
        return

    await message.answer(reply)

    await save_message(row['id'], message.from_user.id, "user", message.text)
    await save_message(row['id'], message.from_user.id, "assistant", reply)
