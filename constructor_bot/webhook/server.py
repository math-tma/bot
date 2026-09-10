from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
import logging

import database
from database import pool
from config import BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_URL
from database import create_pool, close_pool, create_tables
from webhook.bot_manager import (
    process_update, startup_all_bots, shutdown_all_bots
)
from scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Constructor Bot", docs_url=None, redoc_url=None)

# Konstruktor bot
constructor_bot: Bot = None
constructor_dp: Dispatcher = None


async def setup_constructor_bot():
    """Konstruktor botni sozlash"""
    global constructor_bot, constructor_dp

    constructor_bot = Bot(token=BOT_TOKEN)
    constructor_dp = Dispatcher(storage=MemoryStorage())

    # Handlerlarni qo'shish
    from handlers.start import router as start_router
    from handlers.bot_create import router as bot_create_router
    from handlers.my_bots import router as my_bots_router
    from handlers.balance import router as balance_router
    from handlers.referral import router as referral_router
    from handlers.admin import router as admin_router

    constructor_dp.include_router(start_router)
    constructor_dp.include_router(bot_create_router)
    constructor_dp.include_router(my_bots_router)
    constructor_dp.include_router(balance_router)
    constructor_dp.include_router(referral_router)
    constructor_dp.include_router(admin_router)

    # Webhook sozlash
    logger.info(f"🔎 WEBHOOK_URL (repr): {WEBHOOK_URL!r}")
    await constructor_bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True
    )
    logger.info(f"✅ Konstruktor bot webhook: {WEBHOOK_URL}")


# ═══════════════════════════════════════
# STARTUP / SHUTDOWN
# ═══════════════════════════════════════

@app.on_event("startup")
async def on_startup():
    logger.info("🚀 Server ishga tushmoqda...")

    # Database
    await create_pool()
    await create_tables()

    # Konstruktor bot
    await setup_constructor_bot()

    # Barcha shablon botlar
    await startup_all_bots()

    # Scheduler (kunlik yechish)
    await start_scheduler(constructor_bot)

    logger.info("✅ Server tayyor!")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("🔌 Server to'xtatilmoqda...")

    await stop_scheduler()
    await shutdown_all_bots()

    if constructor_bot:
        await constructor_bot.delete_webhook()
        await constructor_bot.session.close()

    await close_pool()
    logger.info("✅ Server to'xtatildi")


# ═══════════════════════════════════════
# WEBHOOK ENDPOINTLAR
# ═══════════════════════════════════════

@app.post(WEBHOOK_PATH)
async def constructor_webhook(request: Request):
    """Konstruktor bot webhook"""
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data)
        await constructor_dp.feed_update(constructor_bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Konstruktor webhook xato: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/{token}")
async def template_bot_webhook(token: str, request: Request):
    """Shablon botlar webhook"""
    try:
        update_data = await request.json()
        await process_update(token, update_data)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Template webhook xato ({token[:15]}...): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Server holati tekshirish"""
    from webhook.bot_manager import running_bots
    return {
        "status": "ok",
        "running_bots": len(running_bots),
    }
