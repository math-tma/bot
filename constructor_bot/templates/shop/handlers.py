from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
import asyncio

import database
from database import pool
from templates.shop.keyboards import (
    subscription_kb, main_menu_kb, categories_kb, products_kb,
    product_detail_kb, cart_kb, order_status_kb,
    admin_main_kb, admin_cats_kb, admin_cat_detail_kb,
    admin_product_kb, back_admin_kb
)

router = Router()


class ShopStates(StatesGroup):
    # Checkout
    waiting_name = State()
    waiting_phone = State()
    waiting_address = State()
    # Admin - kategoriya
    add_cat_name = State()
    # Admin - mahsulot
    add_product_name = State()
    add_product_price = State()
    add_product_desc = State()
    add_product_photo = State()
    # Admin - broadcast
    broadcast_text = State()
    # Admin - kanal
    add_channel_id = State()
    add_channel_name = State()
    add_channel_url = State()


# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════

async def get_bot_row(bot: Bot) -> dict | None:
    bot_info = await bot.get_me()
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, admin_id FROM bots WHERE bot_username = $1",
            bot_info.username
        )
        return dict(row) if row else None


async def check_sub(bot: Bot, user_id: int, bot_id: int) -> tuple[bool, list]:
    async with database.pool.acquire() as conn:
        channels = await conn.fetch(
            "SELECT * FROM bot_required_channels WHERE bot_id = $1", bot_id
        )
    if not channels:
        return True, []
    not_sub = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch['channel_id'], user_id)
            if m.status in ['left', 'kicked', 'banned']:
                not_sub.append(dict(ch))
        except Exception:
            not_sub.append(dict(ch))
    return len(not_sub) == 0, not_sub


async def is_admin_user(bot: Bot, user_id: int) -> bool:
    row = await get_bot_row(bot)
    return row and row['admin_id'] == user_id


async def register_user(bot_id: int, user_id: int, username: str):
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO kinobot_users (bot_id, user_id, username)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
        """, bot_id, user_id, username)


# ═══════════════════════════════════════
# FOYDALANUVCHI — START
# ═══════════════════════════════════════

@router.message(CommandStart())
async def shop_start(message: Message, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return
    bot_id = row['id']
    user_id = message.from_user.id

    await register_user(bot_id, user_id, message.from_user.username or "")

    ok, not_sub = await check_sub(bot, user_id, bot_id)
    if not ok:
        await message.answer(
            "📢 Botdan foydalanish uchun obuna bo'ling:",
            reply_markup=subscription_kb(not_sub)
        )
        return

    is_admin = await is_admin_user(bot, user_id)
    await message.answer(
        "🛒 <b>Do'kon botiga xush kelibsiz!</b>\n\n"
        "Quyidagi bo'limlardan birini tanlang 👇",
        reply_markup=main_menu_kb(is_admin),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "shop_check_sub")
async def shop_check_sub(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return
    ok, not_sub = await check_sub(bot, callback.from_user.id, row['id'])
    if not ok:
        await callback.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)
        return
    await callback.answer("✅ Obuna tasdiqlandi!")
    is_admin = await is_admin_user(bot, callback.from_user.id)
    await callback.message.edit_text(
        "🛒 <b>Do'kon botiga xush kelibsiz!</b>\n\nQuyidagi bo'limlardan birini tanlang 👇",
        reply_markup=main_menu_kb(is_admin),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "shop_main")
async def shop_main(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    is_admin = await is_admin_user(bot, callback.from_user.id)
    await callback.message.edit_text(
        "🛒 <b>Asosiy menyu</b>",
        reply_markup=main_menu_kb(is_admin),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# KATALOG
# ═══════════════════════════════════════

@router.callback_query(F.data == "shop_catalog")
async def shop_catalog(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    if not row:
        return

    async with database.pool.acquire() as conn:
        cats = await conn.fetch("""
            SELECT id, name FROM shop_categories
            WHERE bot_id = $1 ORDER BY position, id
        """, row['id'])

    if not cats:
        await callback.answer("📦 Hali mahsulotlar yo'q!", show_alert=True)
        return

    await callback.message.edit_text(
        "📂 <b>Kategoriyalar</b>\n\nBo'limni tanlang:",
        reply_markup=categories_kb([dict(c) for c in cats]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop_cat_"))
async def shop_category(callback: CallbackQuery, bot: Bot):
    cat_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        cat = await conn.fetchrow(
            "SELECT name FROM shop_categories WHERE id = $1", cat_id
        )
        products = await conn.fetch("""
            SELECT id, name, price, description, photo_id
            FROM shop_products
            WHERE category_id = $1 AND bot_id = $2 AND is_available = TRUE
        """, cat_id, row['id'])

    if not products:
        await callback.answer("📦 Bu kategoriyada mahsulot yo'q!", show_alert=True)
        return

    await callback.message.edit_text(
        f"📂 <b>{cat['name']}</b>\n\nMahsulotni tanlang:",
        reply_markup=products_kb([dict(p) for p in products], cat_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop_product_"))
async def shop_product_detail(callback: CallbackQuery, bot: Bot):
    product_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        product = await conn.fetchrow(
            "SELECT * FROM shop_products WHERE id = $1", product_id
        )

    if not product:
        await callback.answer("❌ Mahsulot topilmadi!", show_alert=True)
        return

    text = (
        f"📦 <b>{product['name']}</b>\n\n"
        f"💰 Narx: <b>{product['price']:,} so'm</b>\n"
    )
    if product['description']:
        text += f"\n📝 {product['description']}"

    if product['photo_id']:
        await callback.message.answer_photo(
            photo=product['photo_id'],
            caption=text,
            reply_markup=product_detail_kb(product_id),
            parse_mode="HTML"
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            text,
            reply_markup=product_detail_kb(product_id),
            parse_mode="HTML"
        )
    await callback.answer()


# ═══════════════════════════════════════
# SAVATCHA
# ═══════════════════════════════════════

@router.callback_query(F.data.startswith("shop_add_cart_"))
async def shop_add_to_cart(callback: CallbackQuery, bot: Bot):
    product_id = int(callback.data.split("_")[-1])
    row = await get_bot_row(bot)
    user_id = callback.from_user.id

    async with database.pool.acquire() as conn:
        product = await conn.fetchrow(
            "SELECT name FROM shop_products WHERE id = $1", product_id
        )
        await conn.execute("""
            INSERT INTO shop_carts (bot_id, user_id, product_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (bot_id, user_id, product_id)
            DO UPDATE SET quantity = shop_carts.quantity + 1
        """, row['id'], user_id, product_id)

    await callback.answer(
        f"✅ {product['name']} savatchaga qo'shildi!",
        show_alert=False
    )


@router.callback_query(F.data == "shop_cart")
async def shop_cart_view(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)
    user_id = callback.from_user.id

    async with database.pool.acquire() as conn:
        items = await conn.fetch("""
            SELECT sc.id as cart_id, sc.quantity,
                   sp.name, sp.price
            FROM shop_carts sc
            JOIN shop_products sp ON sc.product_id = sp.id
            WHERE sc.bot_id = $1 AND sc.user_id = $2
        """, row['id'], user_id)

    if not items:
        await callback.message.edit_text(
            "🛒 <b>Savatcha bo'sh</b>\n\nKatalogdan mahsulot tanlang.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    items_list = [dict(i) for i in items]
    total = sum(i['price'] * i['quantity'] for i in items_list)

    lines = []
    for item in items_list:
        lines.append(
            f"• {item['name']} x{item['quantity']} = "
            f"{item['price'] * item['quantity']:,} so'm"
        )

    await callback.message.edit_text(
        f"🛒 <b>Savatcha</b>\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Jami: <b>{total:,} so'm</b>",
        reply_markup=cart_kb(items_list),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop_remove_"))
async def shop_remove_from_cart(callback: CallbackQuery):
    cart_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM shop_carts WHERE id = $1", cart_id)
    await callback.answer("✅ O'chirildi!")
    await shop_cart_view(callback, callback.bot)


# ═══════════════════════════════════════
# CHECKOUT — BUYURTMA BERISH
# ═══════════════════════════════════════

@router.callback_query(F.data == "shop_checkout")
async def shop_checkout_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ShopStates.waiting_name)
    await callback.message.edit_text(
        "📝 <b>Buyurtma berish</b>\n\n"
        "Ismingizni kiriting:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ShopStates.waiting_name)
async def checkout_name(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(ShopStates.waiting_phone)
    await message.answer("📞 Telefon raqamingizni kiriting:\nMasalan: +998901234567")


@router.message(ShopStates.waiting_phone)
async def checkout_phone(message: Message, state: FSMContext):
    await state.update_data(customer_phone=message.text.strip())
    await state.set_state(ShopStates.waiting_address)
    await message.answer("📍 Yetkazib berish manzilini kiriting:")


@router.message(ShopStates.waiting_address)
async def checkout_address(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    row = await get_bot_row(bot)
    bot_id = row['id']
    user_id = message.from_user.id

    async with database.pool.acquire() as conn:
        items = await conn.fetch("""
            SELECT sc.quantity, sp.name, sp.price, sp.id as product_id
            FROM shop_carts sc
            JOIN shop_products sp ON sc.product_id = sp.id
            WHERE sc.bot_id = $1 AND sc.user_id = $2
        """, bot_id, user_id)

    if not items:
        await state.clear()
        await message.answer("❌ Savatcha bo'sh!")
        return

    items_list = [dict(i) for i in items]
    total = sum(i['price'] * i['quantity'] for i in items_list)

    async with database.pool.acquire() as conn:
        order_id = await conn.fetchval("""
            INSERT INTO shop_orders
            (bot_id, user_id, username, full_name, phone, address, items, total_price, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'new')
            RETURNING id
        """,
            bot_id, user_id,
            message.from_user.username or "",
            data['customer_name'],
            data['customer_phone'],
            message.text.strip(),
            json.dumps(items_list, ensure_ascii=False),
            total
        )
        # Savatchani tozalash
        await conn.execute(
            "DELETE FROM shop_carts WHERE bot_id = $1 AND user_id = $2",
            bot_id, user_id
        )

    await state.clear()

    lines = [f"• {i['name']} x{i['quantity']}" for i in items_list]
    order_text = (
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"📦 Buyurtma #{order_id}\n"
        f"👤 {data['customer_name']}\n"
        f"📞 {data['customer_phone']}\n"
        f"📍 {message.text.strip()}\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Jami: <b>{total:,} so'm</b>\n\n"
        f"⏳ Admin tasdiqlaganidan so'ng xabar yuboriladi."
    )

    await message.answer(order_text, reply_markup=main_menu_kb(), parse_mode="HTML")

    # Adminga xabar
    admin_text = (
        f"🛍️ <b>Yangi buyurtma #{order_id}</b>\n\n"
        f"👤 {data['customer_name']}\n"
        f"📱 @{message.from_user.username or 'yo\'q'}\n"
        f"📞 {data['customer_phone']}\n"
        f"📍 {message.text.strip()}\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Jami: <b>{total:,} so'm</b>"
    )

    try:
        await bot.send_message(
            row['admin_id'],
            admin_text,
            reply_markup=order_status_kb(order_id),
            parse_mode="HTML"
        )
    except Exception:
        pass


# ═══════════════════════════════════════
# BUYURTMALAR TARIXI
# ═══════════════════════════════════════

@router.callback_query(F.data == "shop_orders")
async def shop_user_orders(callback: CallbackQuery, bot: Bot):
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        orders = await conn.fetch("""
            SELECT id, total_price, status, created_at
            FROM shop_orders
            WHERE bot_id = $1 AND user_id = $2
            ORDER BY created_at DESC LIMIT 10
        """, row['id'], callback.from_user.id)

    if not orders:
        await callback.message.edit_text(
            "📦 <b>Buyurtmalarim</b>\n\nHali buyurtmalar yo'q.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    status_icons = {
        'new': '🆕', 'accepted': '✅',
        'delivered': '🚚', 'rejected': '❌'
    }
    lines = []
    for o in orders:
        icon = status_icons.get(o['status'], '❓')
        date = o['created_at'].strftime('%d.%m')
        lines.append(f"{icon} #{o['id']} — {o['total_price']:,} so'm ({date})")

    await callback.message.edit_text(
        "📦 <b>Buyurtmalarim:</b>\n\n" + "\n".join(lines),
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ═══════════════════════════════════════
# ADMIN — BUYURTMA BOSHQARUV
# ═══════════════════════════════════════

async def update_order_status(callback: CallbackQuery, bot: Bot, order_id: int, status: str):
    status_texts = {
        'accepted': '✅ Qabul qilindi',
        'delivered': '🚚 Yetkazildi',
        'rejected': '❌ Rad etildi'
    }

    async with database.pool.acquire() as conn:
        order = await conn.fetchrow(
            "SELECT * FROM shop_orders WHERE id = $1", order_id
        )
        if not order:
            await callback.answer("❌ Buyurtma topilmadi!", show_alert=True)
            return

        await conn.execute(
            "UPDATE shop_orders SET status = $1, updated_at = NOW() WHERE id = $2",
            status, order_id
        )

    status_text = status_texts.get(status, status)
    await callback.answer(f"{status_text}!", show_alert=True)

    try:
        await bot.send_message(
            order['user_id'],
            f"📦 <b>Buyurtma #{order_id}</b> holati yangilandi:\n\n{status_text}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("shop_ord_accept_"))
async def order_accept(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await update_order_status(callback, bot, order_id, 'accepted')


@router.callback_query(F.data.startswith("shop_ord_deliver_"))
async def order_deliver(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await update_order_status(callback, bot, order_id, 'delivered')


@router.callback_query(F.data.startswith("shop_ord_reject_"))
async def order_reject(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    order_id = int(callback.data.split("_")[-1])
    await update_order_status(callback, bot, order_id, 'rejected')


# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════

@router.message(Command("admin"))
async def shop_admin(message: Message, bot: Bot):
    if not await is_admin_user(bot, message.from_user.id):
        return
    await message.answer("👨‍💼 <b>Admin panel</b>", reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "shop_admin")
async def shop_admin_cb(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "👨‍💼 <b>Admin panel</b>",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Kategoriyalar ──

@router.callback_query(F.data == "shop_admin_cats")
async def shop_admin_cats(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        cats = await conn.fetch(
            "SELECT id, name FROM shop_categories WHERE bot_id = $1 ORDER BY position",
            row['id']
        )

    await callback.message.edit_text(
        f"📂 <b>Kategoriyalar ({len(cats)} ta)</b>",
        reply_markup=admin_cats_kb([dict(c) for c in cats]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "shop_add_cat")
async def shop_add_cat_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(ShopStates.add_cat_name)
    await callback.message.edit_text("📂 Kategoriya nomini kiriting:")
    await callback.answer()


@router.message(ShopStates.add_cat_name)
async def shop_add_cat_save(message: Message, state: FSMContext, bot: Bot):
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO shop_categories (bot_id, name) VALUES ($1, $2)
        """, row['id'], message.text.strip())
    await state.clear()
    await message.answer(
        f"✅ <b>{message.text.strip()}</b> kategoriyasi qo'shildi!",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("shop_admin_cat_"))
async def shop_admin_cat_detail(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    cat_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        cat = await conn.fetchrow("SELECT * FROM shop_categories WHERE id = $1", cat_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM shop_products WHERE category_id = $1", cat_id
        )

    await callback.message.edit_text(
        f"📂 <b>{cat['name']}</b>\n\n"
        f"📦 Mahsulotlar: {count} ta",
        reply_markup=admin_cat_detail_kb(cat_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop_del_cat_"))
async def shop_del_cat(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    cat_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM shop_categories WHERE id = $1", cat_id)
    await callback.answer("✅ Kategoriya o'chirildi!", show_alert=True)
    await shop_admin_cats(callback, bot)


# ── Mahsulotlar ──

@router.callback_query(F.data.startswith("shop_add_product_"))
async def shop_add_product_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    cat_id = int(callback.data.split("_")[-1])
    await state.set_state(ShopStates.add_product_name)
    await state.update_data(cat_id=cat_id)
    await callback.message.edit_text("📦 Mahsulot nomini kiriting:")
    await callback.answer()


@router.message(ShopStates.add_product_name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await state.set_state(ShopStates.add_product_price)
    await message.answer("💰 Narxini kiriting (so'mda):")


@router.message(ShopStates.add_product_price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting.")
        return
    await state.update_data(product_price=price)
    await state.set_state(ShopStates.add_product_desc)
    await message.answer("📝 Tavsif kiriting (yoki — yuboring):")


@router.message(ShopStates.add_product_desc)
async def add_product_desc(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "—" else message.text.strip()
    await state.update_data(product_desc=desc)
    await state.set_state(ShopStates.add_product_photo)
    await message.answer("🖼️ Rasm yuboring (yoki — yuboring):")


@router.message(ShopStates.add_product_photo)
async def add_product_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    row = await get_bot_row(bot)

    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.strip() == "—":
        photo_id = None
    else:
        await message.answer("❌ Rasm yuboring yoki — yozing.")
        return

    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO shop_products
            (category_id, bot_id, name, price, description, photo_id)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, data['cat_id'], row['id'], data['product_name'],
            data['product_price'], data['product_desc'], photo_id)

    await state.clear()
    await message.answer(
        f"✅ <b>{data['product_name']}</b> qo'shildi!\n"
        f"💰 Narx: {data['product_price']:,} so'm",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("shop_admin_products_"))
async def shop_admin_products(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    cat_id = int(callback.data.split("_")[-1])

    async with database.pool.acquire() as conn:
        products = await conn.fetch(
            "SELECT id, name, price FROM shop_products WHERE category_id = $1",
            cat_id
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"{p['name']} — {p['price']:,} so'm",
            callback_data=f"shop_del_product_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(
        text="◀️ Orqaga", callback_data=f"shop_admin_cat_{cat_id}"
    )])

    await callback.message.edit_text(
        f"📦 Mahsulotlar ({len(products)} ta)\nO'chirish uchun bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop_del_product_"))
async def shop_del_product(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    product_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM shop_products WHERE id = $1", product_id)
    await callback.answer("✅ Mahsulot o'chirildi!", show_alert=True)


# ── Buyurtmalar tarixi ──

@router.callback_query(F.data == "shop_admin_orders")
async def shop_admin_orders(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        orders = await conn.fetch("""
            SELECT id, full_name, total_price, status, created_at
            FROM shop_orders WHERE bot_id = $1 AND status = 'new'
            ORDER BY created_at DESC
        """, row['id'])

    if not orders:
        await callback.answer("✅ Yangi buyurtmalar yo'q!", show_alert=True)
        return

    lines = [
        f"🆕 #{o['id']} — {o['full_name']} — {o['total_price']:,} so'm"
        for o in orders
    ]

    await callback.message.edit_text(
        "🆕 <b>Yangi buyurtmalar:</b>\n\n" + "\n".join(lines),
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "shop_admin_history")
async def shop_admin_history(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        orders = await conn.fetch("""
            SELECT id, full_name, total_price, status, created_at
            FROM shop_orders
            WHERE bot_id = $1 AND status IN ('delivered', 'rejected')
            ORDER BY created_at DESC LIMIT 20
        """, row['id'])

    if not orders:
        await callback.answer("📋 Tarix bo'sh!", show_alert=True)
        return

    status_icons = {'delivered': '✅', 'rejected': '❌'}
    lines = [
        f"{status_icons.get(o['status'], '?')} #{o['id']} — "
        f"{o['full_name']} — {o['total_price']:,} so'm"
        for o in orders
    ]

    await callback.message.edit_text(
        "📋 <b>Buyurtmalar tarixi:</b>\n\n" + "\n".join(lines),
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Statistika ──

@router.callback_query(F.data == "shop_admin_stats")
async def shop_admin_stats(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    bot_id = row['id']

    async with database.pool.acquire() as conn:
        total_orders = await conn.fetchval(
            "SELECT COUNT(*) FROM shop_orders WHERE bot_id = $1", bot_id
        )
        delivered = await conn.fetchval(
            "SELECT COUNT(*) FROM shop_orders WHERE bot_id = $1 AND status = 'delivered'", bot_id
        )
        total_revenue = await conn.fetchval("""
            SELECT COALESCE(SUM(total_price), 0) FROM shop_orders
            WHERE bot_id = $1 AND status = 'delivered'
        """, bot_id)
        products_count = await conn.fetchval(
            "SELECT COUNT(*) FROM shop_products WHERE bot_id = $1", bot_id
        )

    await callback.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"📦 Jami buyurtmalar: <b>{total_orders}</b>\n"
        f"✅ Yetkazilganlar: <b>{delivered}</b>\n"
        f"💰 Jami daromad: <b>{total_revenue:,} so'm</b>\n"
        f"🛍️ Mahsulotlar: <b>{products_count}</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Xabar yuborish ──

@router.callback_query(F.data == "shop_admin_broadcast")
async def shop_broadcast_start(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(ShopStates.broadcast_text)
    await callback.message.edit_text("📣 Barcha foydalanuvchilarga xabar yozing:")
    await callback.answer()


@router.message(ShopStates.broadcast_text)
async def shop_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    row = await get_bot_row(bot)

    async with database.pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT DISTINCT user_id FROM shop_orders WHERE bot_id = $1", row['id']
        )

    success, failed = 0, 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.html_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(
        f"✅ Yuborildi: {success}\n❌ Yuborilmadi: {failed}",
        reply_markup=back_admin_kb()
    )


# ── Kanallar ──

@router.callback_query(F.data == "shop_admin_channels")
async def shop_channels(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        channels = await conn.fetch(
            "SELECT id, channel_name FROM bot_required_channels WHERE bot_id = $1",
            row['id']
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {ch['channel_name']}",
            callback_data=f"shop_del_ch_{ch['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Qo'shish", callback_data="shop_add_ch")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_admin")])

    await callback.message.edit_text(
        f"📢 Majburiy kanallar ({len(channels)} ta)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "shop_add_ch")
async def shop_add_ch(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    await state.set_state(ShopStates.add_channel_id)
    await callback.message.edit_text("📢 Kanal ID kiriting:")
    await callback.answer()


@router.message(ShopStates.add_channel_id)
async def shop_ch_id(message: Message, state: FSMContext):
    await state.update_data(ch_id=message.text.strip())
    await state.set_state(ShopStates.add_channel_name)
    await message.answer("📝 Kanal nomini kiriting:")


@router.message(ShopStates.add_channel_name)
async def shop_ch_name(message: Message, state: FSMContext):
    await state.update_data(ch_name=message.text.strip())
    await state.set_state(ShopStates.add_channel_url)
    await message.answer("🔗 Kanal URL kiriting:")


@router.message(ShopStates.add_channel_url)
async def shop_ch_url(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    row = await get_bot_row(bot)
    async with database.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_required_channels (bot_id, channel_id, channel_name, channel_url)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, row['id'], data['ch_id'], data['ch_name'], message.text.strip())
    await message.answer(
        f"✅ Kanal qo'shildi: <b>{data['ch_name']}</b>",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("shop_del_ch_"))
async def shop_del_ch(callback: CallbackQuery, bot: Bot):
    if not await is_admin_user(bot, callback.from_user.id):
        return
    ch_id = int(callback.data.split("_")[-1])
    async with database.pool.acquire() as conn:
        await conn.execute("DELETE FROM bot_required_channels WHERE id = $1", ch_id)
    await callback.answer("✅ O'chirildi!", show_alert=True)
    await shop_channels(callback, bot)
