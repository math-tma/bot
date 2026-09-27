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
        [InlineKeyboardButton(text="⚡ Haiku (tez, arzon)", callback_data="ai_setmodel_claude-haiku-4-5-20251001")],
        [InlineKeyboardButton(text="⚖️ Sonnet (muvozanatli)", callback_data="ai_setmodel_claude-sonnet-5")],
        [InlineKeyboardButton(text="🧠 Opus (kuchli, qimmat)", callback_data="ai_setmodel_claude-opus-5-5")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ai_admin")],
    ])


def clear_history_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, tozalash", callback_data="ai_clear_history_confirm"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="ai_admin"),
        ]
    ])
