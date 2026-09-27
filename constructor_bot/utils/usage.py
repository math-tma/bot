"""
Bot so'rovlarini kuzatish va VIP darajalarni aniqlash.
"""
import asyncio
import logging

import database

logger = logging.getLogger(__name__)

# Har bir bot uchun concurrency semaphore — bitta bot boshqalarni
# "qotirib" qo'ymasligi uchun. Semaphore hajmi botning joriy
# darajasiga (tier) qarab beriladi (standart = 10, VIP = 80 va h.k.)
_bot_semaphores: dict[int, asyncio.Semaphore] = {}
_bot_semaphore_limits: dict[int, int] = {}


def get_bot_semaphore(bot_id: int, max_concurrent: int = 10) -> asyncio.Semaphore:
    """
    Bot uchun semaphore qaytaradi. Agar limit o'zgargan bo'lsa
    (masalan tier yangilangan bo'lsa), yangi semaphore yaratiladi.
    """
    current_limit = _bot_semaphore_limits.get(bot_id)
    if bot_id not in _bot_semaphores or current_limit != max_concurrent:
        _bot_semaphores[bot_id] = asyncio.Semaphore(max_concurrent)
        _bot_semaphore_limits[bot_id] = max_concurrent
    return _bot_semaphores[bot_id]


async def track_request(bot_id: int):
    """
    Har bir webhook so'rovi kelganda chaqiriladi — kunlik hisobni
    +1 oshiradi. Tez ishlashi kerak, xato bo'lsa ham asosiy
    jarayonni to'xtatmasligi kerak (shuning uchun try/except).
    """
    try:
        async with database.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO bot_request_stats (bot_id, stat_date, request_count)
                VALUES ($1, CURRENT_DATE, 1)
                ON CONFLICT (bot_id, stat_date)
                DO UPDATE SET request_count = bot_request_stats.request_count + 1
            """, bot_id)
    except Exception as e:
        logger.warning(f"So'rovni hisoblashda xato (bot_id={bot_id}): {e}")


async def get_today_request_count(bot_id: int) -> int:
    """Bugungi so'rovlar sonini qaytaradi."""
    async with database.pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT request_count FROM bot_request_stats
            WHERE bot_id = $1 AND stat_date = CURRENT_DATE
        """, bot_id)
        return count or 0


async def get_yesterday_request_count(bot_id: int) -> int:
    """Kechagi so'rovlar sonini qaytaradi (kunlik billing uchun)."""
    async with database.pool.acquire() as conn:
        count = await conn.fetchval("""
            SELECT request_count FROM bot_request_stats
            WHERE bot_id = $1 AND stat_date = CURRENT_DATE - INTERVAL '1 day'
        """, bot_id)
        return count or 0


async def get_all_tiers() -> list[dict]:
    """Barcha narx darajalarini tartib bo'yicha qaytaradi."""
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM pricing_tiers ORDER BY sort_order ASC
        """)
        return [dict(r) for r in rows]


async def get_tier_for_request_count(request_count: int) -> dict:
    """
    Berilgan so'rovlar soniga mos darajani topadi.
    Hech qanday daraja topilmasa, eng past (standart) darajani qaytaradi.
    """
    tiers = await get_all_tiers()
    for tier in tiers:
        if request_count >= tier['min_requests'] and (
            tier['max_requests'] is None or request_count <= tier['max_requests']
        ):
            return tier
    return tiers[0] if tiers else {
        'tier_name': 'Standart', 'daily_price': 1000, 'max_concurrent': 10
    }


async def get_bot_current_tier(bot_id: int) -> dict:
    """
    Bot uchun joriy tarifni aniqlaydi — kechagi so'rovlar soniga
    asoslanadi. Agar kechagi ma'lumot yo'q bo'lsa (yangi bot),
    standart darajadan boshlanadi.
    """
    yesterday_count = await get_yesterday_request_count(bot_id)
    return await get_tier_for_request_count(yesterday_count)
