import asyncpg
from config import DATABASE_URL

# Global pool
pool: asyncpg.Pool = None


async def create_pool():
    """PostgreSQL connection pool yaratish"""
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
        command_timeout=60
    )
    print("✅ Database ulanish muvaffaqiyatli!")
    return pool


async def close_pool():
    """Pool ni yopish"""
    global pool
    if pool:
        await pool.close()
        print("🔌 Database ulanish yopildi.")


async def get_pool() -> asyncpg.Pool:
    """Pool ni qaytarish"""
    return pool


# ═══════════════════════════════════════
# JADVALLARNI YARATISH
# ═══════════════════════════════════════
async def create_tables():
    """Barcha jadvallarni yaratish"""
    async with pool.acquire() as conn:

        # ── SETTINGS (tizim sozlamalari) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Default sozlamalarni qo'shish
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES
                ('trial_days', '7'),
                ('daily_price', '3000'),
                ('referral_bonus', '5000'),
                ('payment_card', ''),
                ('referral_enabled', 'true'),
                ('maintenance_mode', 'false')
            ON CONFLICT (key) DO NOTHING
        """)

        # ── REQUIRED CHANNELS (majburiy kanallar) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL UNIQUE,
                channel_name TEXT NOT NULL,
                channel_url TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── USERS ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                balance INTEGER DEFAULT 0,
                trial_ends_at TIMESTAMP,
                trial_used BOOLEAN DEFAULT FALSE,
                referred_by BIGINT REFERENCES users(user_id),
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── BOTS (yaratilgan botlar) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                bot_token TEXT NOT NULL UNIQUE,
                bot_username TEXT,
                admin_id BIGINT NOT NULL,
                template_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                is_running BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                last_charged_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── PAYMENTS (to'lovlar) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                check_file_id TEXT,
                confirmed_by BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
        """)

        # ── DAILY CHARGES (kunlik yechishlar) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_charges (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                bot_id INTEGER REFERENCES bots(id),
                amount INTEGER NOT NULL,
                charged_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── REFERRALS ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT REFERENCES users(user_id),
                referred_id BIGINT REFERENCES users(user_id),
                bonus_amount INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ═══════════════════════════════════
        # SHABLON BOTLAR JADVALLARI
        # ═══════════════════════════════════

        # ── QUIZ BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_settings (
                bot_id INTEGER PRIMARY KEY REFERENCES bots(id),
                questions_count INTEGER DEFAULT 10,
                time_per_question INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                question TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_answer CHAR(1) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_results (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                username TEXT,
                full_name TEXT,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                completed_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_banned_users (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                banned_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, user_id)
            )
        """)

        # ── SHOP BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_categories (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                name TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_products (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES shop_categories(id),
                bot_id INTEGER REFERENCES bots(id),
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT,
                photo_id TEXT,
                is_available BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_carts (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                product_id INTEGER REFERENCES shop_products(id),
                quantity INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, user_id, product_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_orders (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                address TEXT,
                items JSONB NOT NULL,
                total_price INTEGER NOT NULL,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── BROADCASTER BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcaster_channels (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                channel_id TEXT NOT NULL,
                channel_name TEXT,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, channel_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcaster_messages (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                channel_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                text TEXT,
                file_id TEXT,
                schedule_type TEXT NOT NULL,
                scheduled_at TIMESTAMP,
                cron_expression TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                last_sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ── REFERRAL BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_bot_settings (
                bot_id INTEGER PRIMARY KEY REFERENCES bots(id),
                bonus_per_referral INTEGER DEFAULT 1000,
                min_withdrawal INTEGER DEFAULT 10000,
                payment_card TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_bot_users (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                balance INTEGER DEFAULT 0,
                referred_by BIGINT,
                is_banned BOOLEAN DEFAULT FALSE,
                joined_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, user_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_bot_withdrawals (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL,
                card_number TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
        """)

        # ── KINO BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kinobot_movies (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                file_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, code)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kinobot_users (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                user_id BIGINT NOT NULL,
                username TEXT,
                is_banned BOOLEAN DEFAULT FALSE,
                joined_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, user_id)
            )
        """)

        # ── BOT REQUIRED CHANNELS (shablon botlar uchun) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_required_channels (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id),
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(bot_id, channel_id)
            )
        """)

        # ── BOT REQUEST STATS (VIP darajalash uchun kunlik so'rovlar hisobi) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_request_stats (
                bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE,
                stat_date DATE NOT NULL DEFAULT CURRENT_DATE,
                request_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bot_id, stat_date)
            )
        """)

        # ── PRICING TIERS (VIP darajalar sozlamalari) ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pricing_tiers (
                id SERIAL PRIMARY KEY,
                tier_name TEXT NOT NULL UNIQUE,
                min_requests INTEGER NOT NULL,
                max_requests INTEGER,
                daily_price INTEGER NOT NULL,
                max_concurrent INTEGER NOT NULL DEFAULT 10,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)

        existing_tiers = await conn.fetchval("SELECT COUNT(*) FROM pricing_tiers")
        if existing_tiers == 0:
            await conn.execute("""
                INSERT INTO pricing_tiers
                    (tier_name, min_requests, max_requests, daily_price, max_concurrent, sort_order)
                VALUES
                    ('Standart', 0, 1000, 1000, 10, 1),
                    ('O''sish', 1001, 5000, 2500, 20, 2),
                    ('Biznes', 5001, 15000, 5000, 40, 3),
                    ('VIP', 15001, NULL, 8000, 80, 4)
            """)

        # ── AI AGENT BOT ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_agent_settings (
                bot_id INTEGER PRIMARY KEY REFERENCES bots(id) ON DELETE CASCADE,
                api_key TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'claude-sonnet-5',
                max_history INTEGER NOT NULL DEFAULT 10,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_agent_messages (
                id SERIAL PRIMARY KEY,
                bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        print("✅ Barcha jadvallar yaratildi!")


# ═══════════════════════════════════════
# SETTINGS FUNKSIYALARI
# ═══════════════════════════════════════
async def get_setting(key: str) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE key = $1", key
        )
        return row["value"] if row else None


async def set_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2
        """, key, value)
