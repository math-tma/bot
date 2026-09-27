from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_kb() -> InlineKeyboardMarkup:
    """Admin asosiy panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="💳 To'lovlar", callback_data="admin_payments")],
        [InlineKeyboardButton(text="🤖 Botlar", callback_data="admin_bots")],
        [InlineKeyboardButton(text="💎 Tariflar (VIP)", callback_data="admin_tiers")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="admin_settings")],
    ])


def admin_users_kb() -> InlineKeyboardMarkup:
    """Foydalanuvchilar panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Ro'yxat", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="🔍 Qidirish", callback_data="admin_users_search")],
        [InlineKeyboardButton(text="🚫 Banlangan", callback_data="admin_users_banned")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])


def admin_user_action_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """Foydalanuvchi ustida amallar"""
    ban_text = "✅ Unban" if is_banned else "🚫 Ban"
    ban_data = f"admin_unban_{user_id}" if is_banned else f"admin_ban_{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_text, callback_data=ban_data)],
        [InlineKeyboardButton(text="💰 Balans qo'shish", callback_data=f"admin_add_balance_{user_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_users")],
    ])


def admin_payments_kb() -> InlineKeyboardMarkup:
    """To'lovlar panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Kutayotganlar", callback_data="admin_payments_pending")],
        [InlineKeyboardButton(text="✅ Tasdiqlanganlar", callback_data="admin_payments_confirmed")],
        [InlineKeyboardButton(text="❌ Rad etilganlar", callback_data="admin_payments_rejected")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])


def admin_payment_action_kb(payment_id: int) -> InlineKeyboardMarkup:
    """To'lovni tasdiqlash yoki rad etish"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_confirm_payment_{payment_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_reject_payment_{payment_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_payments_pending")],
    ])


def admin_bots_kb() -> InlineKeyboardMarkup:
    """Botlar panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Faol botlar", callback_data="admin_bots_active")],
        [InlineKeyboardButton(text="❌ Nofaol botlar", callback_data="admin_bots_inactive")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])


def admin_bot_action_kb(bot_id: int, is_running: bool) -> InlineKeyboardMarkup:
    """Bot ustida amallar"""
    toggle_text = "⏹ To'xtatish" if is_running else "▶️ Ishga tushirish"
    toggle_data = f"admin_stop_bot_{bot_id}" if is_running else f"admin_start_bot_{bot_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)],
        [InlineKeyboardButton(text="🗑️ O'chirish", callback_data=f"admin_delete_bot_{bot_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_bots")],
    ])


def admin_broadcast_kb() -> InlineKeyboardMarkup:
    """Xabar yuborish panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Hammaga", callback_data="admin_broadcast_all")],
        [InlineKeyboardButton(text="✅ Faqat faollarga", callback_data="admin_broadcast_active")],
        [InlineKeyboardButton(text="🎁 Faqat triallarga", callback_data="admin_broadcast_trial")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])


def admin_tiers_kb(tiers: list) -> InlineKeyboardMarkup:
    """Tariflar (VIP darajalar) ro'yxati"""
    buttons = []
    for t in tiers:
        max_r = f"{t['max_requests']:,}" if t['max_requests'] else "∞"
        buttons.append([InlineKeyboardButton(
            text=f"{t['tier_name']} ({t['min_requests']:,}-{max_r}) — {t['daily_price']:,} so'm/kun",
            callback_data=f"admin_tier_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_tier_detail_kb(tier_id: int) -> InlineKeyboardMarkup:
    """Bitta tarifni tahrirlash menyusi"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Narxni o'zgartirish", callback_data=f"admin_tier_price_{tier_id}")],
        [InlineKeyboardButton(text="⚡ Concurrency limitni o'zgartirish", callback_data=f"admin_tier_limit_{tier_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_tiers")],
    ])


def admin_settings_kb() -> InlineKeyboardMarkup:
    """Sozlamalar panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Trial davomiyligi", callback_data="admin_set_trial_days")],
        [InlineKeyboardButton(text="🔗 Referral bonus", callback_data="admin_set_referral_bonus")],
        [InlineKeyboardButton(text="💳 To'lov karta", callback_data="admin_set_payment_card")],
        [InlineKeyboardButton(text="📢 Majburiy kanallar", callback_data="admin_channels")],
        [InlineKeyboardButton(text="🔧 Texnik ishlar", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])


def admin_channels_kb(channels: list) -> InlineKeyboardMarkup:
    """Majburiy kanallar boshqaruvi"""
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {ch['channel_name']}",
            callback_data=f"admin_del_channel_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin_add_channel")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_back_kb() -> InlineKeyboardMarkup:
    """Admin orqaga"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="admin_main")],
    ])
