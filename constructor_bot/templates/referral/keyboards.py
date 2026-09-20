from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def subscription_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['channel_name']}", url=ch['channel_url']
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Tekshirish", callback_data="ref_check_sub"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def phone_kb() -> InlineKeyboardMarkup:
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🔗 Referral havolam", callback_data="ref_link")],
        [InlineKeyboardButton(text="💰 Balans", callback_data="ref_balance")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="ref_leaderboard")],
        [InlineKeyboardButton(text="💸 Pul yechish", callback_data="ref_withdraw")],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="ref_help")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="👨‍💻 Admin panel", callback_data="ref_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def withdraw_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Yechishni tasdiqlash", callback_data="ref_withdraw_confirm")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_main")],
    ])


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_main")],
    ])


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Yechish so'rovlari", callback_data="ref_admin_withdrawals")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="ref_admin_users")],
        [InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="ref_admin_settings")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="ref_admin_broadcast")],
        [InlineKeyboardButton(text="📢 Majburiy kanallar", callback_data="ref_admin_channels")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="ref_admin_stats")],
    ])


def admin_withdrawal_kb(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Tasdiqlash",
            callback_data=f"ref_confirm_w_{withdrawal_id}"
        ),
        InlineKeyboardButton(
            text="❌ Rad etish",
            callback_data=f"ref_reject_w_{withdrawal_id}"
        ),
    ]])


def admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Bonus miqdori", callback_data="ref_set_bonus")],
        [InlineKeyboardButton(text="💸 Min yechish", callback_data="ref_set_min_withdraw")],
        [InlineKeyboardButton(text="💳 To'lov karta", callback_data="ref_set_card")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_admin")],
    ])


def admin_user_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_text = "✅ Unban" if is_banned else "🚫 Ban"
    ban_data = f"ref_unban_{user_id}" if is_banned else f"ref_ban_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_text, callback_data=ban_data)],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="ref_admin_users")],
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Admin panel", callback_data="ref_admin")],
    ])
