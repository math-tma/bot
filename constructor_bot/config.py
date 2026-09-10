from dotenv import load_dotenv
import os

load_dotenv()

# ═══════════════════════════════════════
# BOT SOZLAMALARI
# ═══════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL")

# ═══════════════════════════════════════
# WEBHOOK
# ═══════════════════════════════════════
WEBHOOK_HOST = (os.getenv("WEBHOOK_HOST") or "").strip().rstrip("/")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8000))
WEBHOOK_PATH = f"/webhook/constructor"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Shablon botlar uchun webhook
def get_template_webhook_url(token: str) -> str:
    return f"{WEBHOOK_HOST}/webhook/{token}"

# ═══════════════════════════════════════
# BIZNES SOZLAMALARI (DB dan o'qiladi,
# bu yerda faqat default qiymatlar)
# ═══════════════════════════════════════
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", 7))
DAILY_PRICE = int(os.getenv("DAILY_PRICE", 3000))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", 5000))
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "")

# ═══════════════════════════════════════
# SHABLON BOTLAR TURLARI
# ═══════════════════════════════════════
TEMPLATE_TYPES = {
    "quiz": "🎯 Quiz bot",
    "shop": "🛒 Do'kon bot",
    "broadcaster": "📢 Avto xabar bot",
    "referral": "👥 Referral bot",
    "kinobot": "🎬 Kino bot",
}

# ═══════════════════════════════════════
# XABARLAR
# ═══════════════════════════════════════
MESSAGES = {
    "start": (
        "👋 Xush kelibsiz, {name}!\n\n"
        "Bu bot orqali o'zingizga kerakli Telegram botini yaratishingiz mumkin.\n\n"
        "📦 Mavjud shablon botlar:\n"
        "🎯 Quiz bot\n"
        "🛒 Do'kon bot\n"
        "📢 Avto xabar bot\n"
        "👥 Referral bot\n"
        "🎬 Kino bot\n\n"
        "⬇️ Quyidagi tugmalardan birini tanlang:"
    ),
    "subscription_required": (
        "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:\n\n"
        "{channels}\n\n"
        "Obuna bo'lgach, /start buyrug'ini bosing."
    ),
    "trial_info": (
        "🎁 Sizga {days} kunlik sinov muddati berildi!\n"
        "Bu davomda 1 ta bot bepul yaratishingiz mumkin."
    ),
    "balance_empty": (
        "❌ Balansingiz yetarli emas!\n\n"
        "💰 Joriy balans: {balance} so'm\n"
        "📊 Kunlik to'lov: {daily} so'm/bot\n\n"
        "Balansni to'ldiring va botingiz qayta ishga tushadi."
    ),
    "bot_stopped": (
        "⏹ <b>{bot_name}</b> boti to'xtatildi.\n"
        "Sabab: Balans tugadi.\n\n"
        "💳 Balansni to'ldiring va bot qayta ishga tushadi."
    ),
}
