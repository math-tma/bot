from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import database
from database import pool
import asyncio


async def notify_user(bot: Bot, user_id: int, text: str, **kwargs):
    """Bitta foydalanuvchiga xabar yuborish"""
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


async def broadcast_message(bot: Bot, text: str, target: str = "all") -> dict:
    """
    Foydalanuvchilarga ommaviy xabar yuborish.
    target: 'all' | 'active' | 'trial'
    """
    async with database.pool.acquire() as conn:
        if target == "all":
            users = await conn.fetch("""
                SELECT user_id FROM users WHERE is_banned = FALSE
            """)
        elif target == "active":
            users = await conn.fetch("""
                SELECT DISTINCT u.user_id FROM users u
                JOIN bots b ON u.user_id = b.user_id
                WHERE u.is_banned = FALSE AND b.is_running = TRUE
            """)
        elif target == "trial":
            users = await conn.fetch("""
                SELECT user_id FROM users
                WHERE is_banned = FALSE
                AND trial_ends_at > NOW()
            """)
        else:
            users = []

    success = 0
    failed = 0

    for user in users:
        result = await notify_user(bot, user['user_id'], text, parse_mode="HTML")
        if result:
            success += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # Flood limitdan himoya

    return {"success": success, "failed": failed, "total": len(users)}


async def notify_stopped_bots(bot: Bot, stopped_bots: list):
    """Balansi tugagan foydalanuvchilarga xabar yuborish"""
    for item in stopped_bots:
        price_line = ""
        if item.get('daily_price'):
            price_line = (
                f"💵 Kerakli summa: {item['daily_price']:,} so'm/kun "
                f"({item.get('tier', 'Standart')} tarif)\n"
            )
        text = (
            f"⚠️ <b>Bot to'xtatildi!</b>\n\n"
            f"🤖 Bot: @{item.get('bot_username', 'noma\'lum')}\n"
            f"📌 Sabab: Balansingiz tugadi\n"
            f"{price_line}\n"
            f"💳 Balansni to'ldiring va bot avtomatik qayta ishga tushadi."
        )
        await notify_user(bot, item['user_id'], text, parse_mode="HTML")


async def notify_payment_confirmed(bot: Bot, user_id: int, amount: int):
    """To'lov tasdiqlanganda xabar"""
    text = (
        f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
        f"💰 Miqdor: {amount:,} so'm\n\n"
        f"Balansingiz yangilandi. To'xtatilgan botlar qayta ishga tushdi."
    )
    await notify_user(bot, user_id, text, parse_mode="HTML")


async def notify_payment_rejected(bot: Bot, user_id: int, amount: int):
    """To'lov rad etilganda xabar"""
    text = (
        f"❌ <b>To'lovingiz rad etildi!</b>\n\n"
        f"💰 Miqdor: {amount:,} so'm\n\n"
        f"Agar xatolik deb hisoblasangiz, admin bilan bog'laning."
    )
    await notify_user(bot, user_id, text, parse_mode="HTML")
