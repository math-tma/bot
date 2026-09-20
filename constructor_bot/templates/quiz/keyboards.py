from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def subscription_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['channel_name']}", url=ch['channel_url']
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Tekshirish", callback_data="quiz_check_sub"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def start_quiz_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎯 Testni boshlash", callback_data="quiz_start")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="quiz_leaderboard")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="👨‍💻 Admin panel", callback_data="quiz_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def answer_kb(question_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="A", callback_data=f"quiz_ans_{question_index}_A"),
            InlineKeyboardButton(text="B", callback_data=f"quiz_ans_{question_index}_B"),
        ],
        [
            InlineKeyboardButton(text="C", callback_data=f"quiz_ans_{question_index}_C"),
            InlineKeyboardButton(text="D", callback_data=f"quiz_ans_{question_index}_D"),
        ],
    ])


def result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Qayta boshlash", callback_data="quiz_start")],
        [InlineKeyboardButton(text="🏆 Leaderboard", callback_data="quiz_leaderboard")],
    ])


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Savollar yuklash", callback_data="quiz_upload")],
        [InlineKeyboardButton(text="⚙️ Test sozlamalari", callback_data="quiz_settings")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="quiz_users")],
        [InlineKeyboardButton(text="📊 Natijalar", callback_data="quiz_results")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="quiz_broadcast")],
        [InlineKeyboardButton(text="📢 Majburiy kanallar", callback_data="quiz_channels")],
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Admin panel", callback_data="quiz_admin")],
    ])


def users_list_kb(users: list, bot_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for u in users:
        ban_icon = "✅" if not u['is_banned'] else "🚫"
        buttons.append([InlineKeyboardButton(
            text=f"{ban_icon} {u['full_name'] or u['user_id']}",
            callback_data=f"quiz_user_{u['user_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_action_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_text = "✅ Unban" if is_banned else "🚫 Ban"
    ban_data = f"quiz_unban_{user_id}" if is_banned else f"quiz_ban_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_text, callback_data=ban_data)],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="quiz_users")],
    ])
