from aiogram import Bot
from aiogram.enums import ChatMemberStatus
import database
from database import pool
import logging

logger = logging.getLogger(__name__)


async def get_required_channels() -> list:
    """Konstruktor bot uchun majburiy kanallarni olish"""
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, channel_id, channel_name, channel_url
            FROM required_channels
            WHERE is_active = TRUE
        """)
        return [dict(r) for r in rows]


async def check_user_subscription(bot: Bot, user_id: int) -> tuple[bool, list]:
    """
    Foydalanuvchi barcha kanallarga obuna bo'lganligini tekshirish.
    Qaytaradi: (barchasi_obuna, obuna_bolmagan_kanallar)
    """
    channels = await get_required_channels()

    if not channels:
        return True, []

    not_subscribed = []

    for channel in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=channel['channel_id'],
                user_id=user_id
            )
            if member.status in [
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
                ChatMemberStatus.BANNED,
            ]:
                not_subscribed.append(channel)
        except Exception as e:
            logger.warning(
                f"Kanal tekshirishda xato (channel_id={channel['channel_id']}, "
                f"user_id={user_id}): {e}"
            )
            not_subscribed.append(channel)

    return len(not_subscribed) == 0, not_subscribed


async def check_bot_subscription(bot: Bot, user_id: int, bot_id: int) -> tuple[bool, list]:
    """
    Shablon bot uchun majburiy kanallarni tekshirish
    """
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT channel_id, channel_name, channel_url
            FROM bot_required_channels
            WHERE bot_id = $1
        """, bot_id)

    channels = [dict(r) for r in rows]

    if not channels:
        return True, []

    not_subscribed = []

    for channel in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=channel['channel_id'],
                user_id=user_id
            )
            if member.status in [
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
                ChatMemberStatus.BANNED,
            ]:
                not_subscribed.append(channel)
        except Exception as e:
            logger.warning(
                f"Kanal tekshirishda xato (channel_id={channel['channel_id']}, "
                f"user_id={user_id}): {e}"
            )
            not_subscribed.append(channel)

    return len(not_subscribed) == 0, not_subscribed
