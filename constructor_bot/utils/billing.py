from datetime import datetime
import database
from database import pool
from database import get_setting


async def get_user_balance(user_id: int) -> int:
    """Foydalanuvchi balansini olish"""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )
        return row['balance'] if row else 0


async def add_balance(user_id: int, amount: int):
    """Balansga pul qo'shish"""
    async with database.pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET balance = balance + $1 WHERE user_id = $2
        """, amount, user_id)


async def deduct_balance(user_id: int, amount: int) -> bool:
    """
    Balansdan pul yechish.
    Qaytaradi: True — muvaffaqiyatli, False — yetarli emas
    """
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )
        if not row or row['balance'] < amount:
            return False

        await conn.execute("""
            UPDATE users SET balance = balance - $1 WHERE user_id = $2
        """, amount, user_id)
        return True


async def is_trial_active(user_id: int) -> bool:
    """Trial muddati faolligini tekshirish"""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT trial_ends_at FROM users WHERE user_id = $1
        """, user_id)
        if not row or not row['trial_ends_at']:
            return False
        return row['trial_ends_at'] > datetime.now()


async def get_user_bots(user_id: int) -> list:
    """Foydalanuvchi botlarini olish"""
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, bot_token, bot_username, template_type,
                   is_active, is_running, created_at
            FROM bots
            WHERE user_id = $1
            ORDER BY created_at DESC
        """, user_id)
        return [dict(r) for r in rows]


async def get_running_bots_count(user_id: int) -> int:
    """Ishlayotgan botlar sonini olish"""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as cnt FROM bots
            WHERE user_id = $1 AND is_running = TRUE
        """, user_id)
        return row['cnt'] if row else 0


async def can_create_bot(user_id: int) -> tuple[bool, str]:
    """
    Yangi bot yaratish mumkinligini tekshirish.
    Qaytaradi: (mumkin, sabab)
    """
    async with database.pool.acquire() as conn:
        user = await conn.fetchrow("""
            SELECT balance, trial_ends_at, trial_used FROM users
            WHERE user_id = $1
        """, user_id)

        if not user:
            return False, "Foydalanuvchi topilmadi"

        bots_count = await conn.fetchval("""
            SELECT COUNT(*) FROM bots WHERE user_id = $1
        """, user_id)

        # Trial foydalanuvchi — 1 ta bot bepul
        trial_active = user['trial_ends_at'] and user['trial_ends_at'] > datetime.now()
        if trial_active and bots_count == 0:
            return True, "trial"

        # Pullik — balans tekshirish
        daily_price = int(await get_setting('daily_price') or 3000)
        if user['balance'] >= daily_price:
            return True, "paid"

        return False, "Balansingiz yetarli emas. Balansni to'ldiring."


async def process_daily_charges():
    """
    Har kecha ishlaydigan kunlik yechish.
    Har faol bot uchun kunlik to'lov yechiladi.
    """
    daily_price = int(await get_setting('daily_price') or 3000)

    async with database.pool.acquire() as conn:
        # Barcha ishlaydigan botlarni olish
        running_bots = await conn.fetch("""
            SELECT b.id, b.user_id, b.bot_username, b.template_type,
                   u.balance, u.trial_ends_at
            FROM bots b
            JOIN users u ON b.user_id = u.user_id
            WHERE b.is_running = TRUE
        """)

        stopped_bots = []

        for bot in running_bots:
            user_id = bot['user_id']
            bot_id = bot['id']

            # Trial tekshirish
            trial_active = (
                bot['trial_ends_at'] and
                bot['trial_ends_at'] > datetime.now()
            )
            if trial_active:
                continue  # Trial davomida to'lov yo'q

            # Balans tekshirish
            if bot['balance'] >= daily_price:
                # Yechish
                await conn.execute("""
                    UPDATE users SET balance = balance - $1
                    WHERE user_id = $2
                """, daily_price, user_id)

                # Yechish tarixi
                await conn.execute("""
                    INSERT INTO daily_charges (user_id, bot_id, amount)
                    VALUES ($1, $2, $3)
                """, user_id, bot_id, daily_price)

            else:
                # Balans yetarli emas — botni to'xtatish
                await conn.execute("""
                    UPDATE bots SET is_running = FALSE
                    WHERE id = $1
                """, bot_id)

                from webhook.bot_manager import stop_template_bot
                await stop_template_bot(bot_id)

                stopped_bots.append({
                    'user_id': user_id,
                    'bot_username': bot['bot_username'],
                    'bot_id': bot_id,
                })

        return stopped_bots


async def reactivate_bots_if_balance(user_id: int):
    """
    Balans to'ldirilganda to'xtatilgan botlarni qayta ishga tushirish
    """
    daily_price = int(await get_setting('daily_price') or 3000)

    async with database.pool.acquire() as conn:
        balance = await conn.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )

        # To'xtatilgan botlarni olish
        stopped_bots = await conn.fetch("""
            SELECT id, bot_token, bot_username, admin_id, template_type
            FROM bots
            WHERE user_id = $1 AND is_running = FALSE AND is_active = TRUE
        """, user_id)

        reactivated = []
        for bot in stopped_bots:
            if balance >= daily_price:
                await conn.execute("""
                    UPDATE bots SET is_running = TRUE WHERE id = $1
                """, bot['id'])

                from webhook.bot_manager import start_template_bot
                await start_template_bot(dict(bot))

                reactivated.append(dict(bot))

        return reactivated


async def get_payment_history(user_id: int, limit: int = 10) -> list:
    """Foydalanuvchi to'lov tarixi"""
    async with database.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT amount, status, created_at, confirmed_at
            FROM payments
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]
