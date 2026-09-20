from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def subscription_kb(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['channel_name']}", url=ch['channel_url']
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Tekshirish", callback_data="shop_check_sub"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🛍️ Katalog", callback_data="shop_catalog")],
        [InlineKeyboardButton(text="🛒 Savatcha", callback_data="shop_cart")],
        [InlineKeyboardButton(text="📦 Buyurtmalarim", callback_data="shop_orders")],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="👨‍💻 Admin panel", callback_data="shop_admin")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def categories_kb(categories: list) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat['name'],
            callback_data=f"shop_cat_{cat['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_kb(products: list, category_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"{p['name']} — {p['price']:,} so'm",
            callback_data=f"shop_product_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Savatchaga", callback_data=f"shop_add_cart_{product_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_catalog")],
    ])


def cart_kb(items: list) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {item['name']}",
            callback_data=f"shop_remove_{item['cart_id']}"
        )])
    if items:
        buttons.append([InlineKeyboardButton(
            text="✅ Buyurtma berish", callback_data="shop_checkout"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_status_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul", callback_data=f"shop_ord_accept_{order_id}"),
            InlineKeyboardButton(text="🚚 Yetkazildi", callback_data=f"shop_ord_deliver_{order_id}"),
        ],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"shop_ord_reject_{order_id}")],
    ])


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Kategoriyalar", callback_data="shop_admin_cats")],
        [InlineKeyboardButton(text="📦 Buyurtmalar", callback_data="shop_admin_orders")],
        [InlineKeyboardButton(text="📋 Buyurtmalar tarixi", callback_data="shop_admin_history")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="shop_admin_broadcast")],
        [InlineKeyboardButton(text="📢 Majburiy kanallar", callback_data="shop_admin_channels")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="shop_admin_stats")],
    ])


def admin_cats_kb(categories: list) -> InlineKeyboardMarkup:
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=f"📂 {cat['name']}",
            callback_data=f"shop_admin_cat_{cat['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ Kategoriya qo'shish", callback_data="shop_add_cat")])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_cat_detail_kb(cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Mahsulot qo'shish", callback_data=f"shop_add_product_{cat_id}")],
        [InlineKeyboardButton(text="📋 Mahsulotlar", callback_data=f"shop_admin_products_{cat_id}")],
        [InlineKeyboardButton(text="🗑️ Kategoriyani o'chirish", callback_data=f"shop_del_cat_{cat_id}")],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_admin_cats")],
    ])


def admin_product_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑️ O'chirish",
            callback_data=f"shop_del_product_{product_id}"
        )],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data="shop_admin_cats")],
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Admin panel", callback_data="shop_admin")],
    ])
