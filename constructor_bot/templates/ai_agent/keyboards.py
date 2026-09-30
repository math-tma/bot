from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 System prompt", callback_data="ai_prompt")],
        [InlineKeyboardButton(text="🔑 API kalit", callback_data="ai_apikey")],
        [InlineKeyboardButton(text="🧠 Model", callback_data="ai_model")],
        [InlineKeyboardButton(text="🗑 Suhbat tarixini tozalash", callback_data="ai_clear_history")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="ai_stats")],
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Admin panel", callback_data="ai_admin")],
    ])


def model_select_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Flash (tez)", callback_data="ai_setmodel_gemini-2.0-flash")],
        [InlineKeyboardButton(text="⚖️ Pro (kuchli)", callback_data="ai_setmodel_gemini-1.5-pro")],
        [InlineKeyboardButton(text="💫 Flash 1.5 (arzon)", callback_data="ai_setmodel_gemini-1.5-flash")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ai_admin")],
    ])


def clear_history_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, tozalash", callback_data="ai_clear_history_confirm"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="ai_admin"),
        ]
    ])
