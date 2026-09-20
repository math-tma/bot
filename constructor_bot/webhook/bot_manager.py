from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
import asyncio
import logging

import database
from database import pool
from config import WEBHOOK_HOST, get_template_webhook_url

logger = logging.getLogger(__name__)

# Ishlayotgan botlar: {bot_id: {"bot": Bot, "dp": Dispatcher}}
running_bots: dict = {}


def get_template_router(template_type: str):
    """Template turiga qarab router qaytarish"""
    if template_type == "quiz":
        from templates.quiz.handlers import router
        return router
    elif template_type == "shop":
        from templates.shop.handlers import router
        return router
    elif template_type == "broadcaster":
        from templates.broadcaster.handlers import router
        return router
    elif template_type == "referral":
        from templates.referral.handlers import router
        return router
    elif template_type == "kinobot":
        from templates.kinobot.handlers import router
        return router
    return None


async def start_template_bot(bot_data: dict):
    """Shablon botni webhook orqali ishga tushirish"""
    bot_id = bot_data['id']
    token = bot_data['bot_token']
    template_type = bot_data['template_type']

    # Allaqachon ishlayaptimi?
    if bot_id in running_bots:
        logger.info(f"Bot #{bot_id} allaqachon ishlayapti")
        return

    try:
        bot = Bot(token=token)
        dp = Dispatcher(storage=MemoryStorage())

        # Template routerni qo'shish
        router = get_template_router(template_type)
        if router:
            dp.include_router(router)

        # Bot ma'lumotlarini dispatcherga uzatish
        dp["bot_db_id"] = bot_id
        dp["admin_id"] = bot_data['admin_id']

        # Webhookni sozlash
        webhook_url = get_template_webhook_url(token)
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True
        )

        running_bots[bot_id] = {
            "bot": bot,
            "dp": dp,
            "token": token,
        }

        logger.info(f"✅ Bot #{bot_id} (@{bot_data.get('bot_username')}) ishga tushdi")

    except Exception as e:
        logger.error(f"❌ Bot #{bot_id} ishga tushmadi: {e}")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE bots SET is_running = FALSE WHERE id = $1", bot_id
            )


async def stop_template_bot(bot_id: int):
    """Shablon botni to'xtatish"""
    if bot_id not in running_bots:
        return

    try:
        bot_info = running_bots[bot_id]
        bot: Bot = bot_info["bot"]

        await bot.delete_webhook()
        await bot.session.close()

        del running_bots[bot_id]
        logger.info(f"⏹ Bot #{bot_id} to'xtatildi")

    except Exception as e:
        logger.error(f"Bot #{bot_id} to'xtatishda xato: {e}")


async def process_update(token: str, update_data: dict):
    """Webhook dan kelgan updateni qayta ishlash"""
    target_bot = None
    target_dp = None

    for bot_id, info in running_bots.items():
        if info["token"] == token:
            target_bot = info["bot"]
            target_dp = info["dp"]
            break

    if not target_bot or not target_dp:
        logger.warning(f"Token uchun bot topilmadi: {token[:20]}...")
        return

    try:
        update = Update.model_validate(update_data)
        await target_dp.feed_update(target_bot, update)
    except Exception as e:
        logger.error(f"Update qayta ishlashda xato: {e}")


async def startup_all_bots():
    """Server qayta ishga tushganda barcha faol botlarni yuklash"""
    async with database.pool.acquire() as conn:
        bots = await conn.fetch("""
            SELECT id, bot_token, bot_username, admin_id, template_type
            FROM bots WHERE is_running = TRUE
        """)

    logger.info(f"📦 {len(bots)} ta bot yuklanmoqda...")

    for bot_data in bots:
        await start_template_bot(dict(bot_data))
        await asyncio.sleep(0.1)

    logger.info(f"✅ Barcha botlar ishga tushdi")


async def close_bot_session(bot_id: int):
    """
    Server qayta ishga tushganda (deploy/redeploy) chaqiriladi.
    DIQQAT: webhook'ni O'CHIRMAYDI — faqat aiohttp session'ni yopadi.
    Webhook Telegram'da saqlanib qoladi, chunki yangi jarayon (process)
    startup vaqtida uni qayta o'rnatadi. Agar bu yerda delete_webhook()
    chaqirilsa, eski va yangi jarayon orasidagi race condition tufayli
    yangi o'rnatilgan webhook o'chib ketishi mumkin.
    """
    if bot_id not in running_bots:
        return

    try:
        bot_info = running_bots[bot_id]
        bot: Bot = bot_info["bot"]
        await bot.session.close()
        del running_bots[bot_id]
    except Exception as e:
        logger.error(f"Bot #{bot_id} session yopishda xato: {e}")


async def shutdown_all_bots():
    """
    Server to'xtaganda (deploy/redeploy) chaqiriladi.
    Botlarni TO'XTATMAYDI — faqat session'larni yopadi, webhook'lar
    Telegram'da saqlanib qoladi.
    """
    bot_ids = list(running_bots.keys())
    for bot_id in bot_ids:
        await close_bot_session(bot_id)
