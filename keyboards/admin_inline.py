from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import get_product_by_id


class AdminOrdersPaginator(CallbackData, prefix="admin_order_page"):
    action: str
    page: int


class AdminBookingsPaginator(CallbackData, prefix="admin_booking_page"):
    action: str
    page: int
    period: str  # today, week, month


class AdminSetOrderStatus(CallbackData, prefix="admin_set_status"):
    order_id: int
    status: str # 'assembled' или 'shipped'


class AdminEditOrder(CallbackData, prefix="admin_edit_order"):
    action: str  # 'remove_item', 'finish'
    order_id: int
    item_id: str | None = None # ID товара для удаления


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Основная клавиатура админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗓️ Управление записями", callback_data="admin_booking_management")
    builder.button(text="🛍️ Управление заказами", callback_data="admin_order_management")
    builder.button(text="🎁 Управление промокодами", callback_data="admin_promocode_management")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📬 Рассылка", callback_data="admin_broadcast")
    builder.button(text="🚷 Управление блокировками", callback_data="admin_block_management")
    builder.adjust(1)
    return builder.as_markup()

def get_promocode_management_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить промокод", callback_data="admin_add_promocode_start")
    builder.button(text="📋 Показать все промокоды", callback_data="admin_show_promocodes")
    builder.button(text="🔙 Назад", callback_data="admin_back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_promocode_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🛍️ Для магазина", callback_data="admin_add_promo_type_shop")
    builder.button(text="🗓️ Для детейлинга (в разработке)", callback_data="admin_add_promo_type_detailing")
    builder.button(text="🔙 Назад", callback_data="admin_promocode_management")
    builder.adjust(1)
    return builder.as_markup()

def get_booking_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления записями."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Сегодня", callback_data="admin_bookings_today"),
        InlineKeyboardButton(text="Неделя", callback_data="admin_bookings_week"),
        InlineKeyboardButton(text="Месяц", callback_data="admin_bookings_month")
    )
    builder.row(InlineKeyboardButton(text="❌ Отменить запись по ID", callback_data="admin_cancel_booking_start"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    return builder.as_markup()

def get_block_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления блокировками."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔒 Заблокировать", callback_data="admin_block_user"))
    builder.row(InlineKeyboardButton(text="🔓 Разблокировать", callback_data="admin_unblock_user"))
    builder.row(InlineKeyboardButton(text="📋 Показать заблокированных", callback_data="admin_show_blocked"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    return builder.as_markup()

def get_back_to_menu_keyboard(menu_callback: str) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=menu_callback))
    return builder.as_markup()

def get_stats_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню статистики."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📈 По записям (текст)", callback_data="admin_stats_bookings"),
        InlineKeyboardButton(text="🛒 По магазину (текст)", callback_data="admin_stats_shop")
    )
    builder.row(
        InlineKeyboardButton(text="📊 График по услугам", callback_data="admin_chart_bookings"),
        InlineKeyboardButton(text="📊 График по промокодам", callback_data="admin_chart_shop")
    )
    builder.row(
        InlineKeyboardButton(text="📄 Экспорт записей (CSV)", callback_data="admin_export_bookings_csv"),
        InlineKeyboardButton(text="📄 Экспорт заказов (CSV)", callback_data="admin_export_orders_csv")
    )
    builder.row(InlineKeyboardButton(text="📅 Статистика за период", callback_data="admin_stats_custom_period"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    return builder.as_markup()

def get_order_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления заказами."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Посмотреть последние заказы", callback_data="admin_last_orders"))
    builder.row(InlineKeyboardButton(text="✏️ Изменить состав заказа", callback_data="admin_edit_order_start"))
    builder.row(InlineKeyboardButton(text="🔄 Изменить статус заказа", callback_data="admin_change_order_status_start"))
    builder.row(InlineKeyboardButton(text="❌ Отменить заказ по ID", callback_data="admin_cancel_order_start"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_to_main"))
    return builder.as_markup()


def get_broadcast_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения рассылки."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚀 Отправить всем", callback_data="admin_broadcast_confirm"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_broadcast_cancel"))
    return builder.as_markup()


def get_admin_paginator(page: int, total_pages: int, paginator_type: AdminOrdersPaginator | AdminBookingsPaginator, back_callback: str) -> InlineKeyboardMarkup:
    """Универсальный пагинатор для админки."""
    builder = InlineKeyboardBuilder()
    pagination_row = []

    if page > 0:
        pagination_row.append(InlineKeyboardButton(text="< Назад", callback_data=paginator_type(action="prev", page=page).pack()))

    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="ignore_page_count"))

    if page < total_pages - 1:
        pagination_row.append(InlineKeyboardButton(text="Вперед >", callback_data=paginator_type(action="next", page=page).pack()))

    if pagination_row:
        builder.row(*pagination_row)

    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=back_callback))
    return builder.as_markup()


def get_set_order_status_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора нового статуса заказа."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Собран", callback_data=AdminSetOrderStatus(order_id=order_id, status="assembled").pack()))
    builder.row(InlineKeyboardButton(text="🚚 Отправлен", callback_data=AdminSetOrderStatus(order_id=order_id, status="shipped").pack()))
    return builder.as_markup()


def get_new_order_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для уведомления админа о новом заказе."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➡️ К управлению заказами", callback_data="admin_order_management"))
    return builder.as_markup()


async def get_order_editing_keyboard(order: dict) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования состава заказа."""
    builder = InlineKeyboardBuilder()
    cart = order.get('cart', {})
    order_id = order.get('id')

    if not cart:
        builder.row(InlineKeyboardButton(text="Корзина пуста", callback_data="ignore"))
    else:
        for item_id, quantity in cart.items():
            product = await get_product_by_id(item_id) or {}
            product_name = product.get('name', 'Неизвестный товар')
            builder.row(
                InlineKeyboardButton(
                    text=f"{product_name} ({quantity} шт.)",
                    callback_data="ignore"
                ),
                InlineKeyboardButton(
                    text="❌ Удалить 1 шт.",
                    callback_data=AdminEditOrder(action="remove_item", order_id=order_id, item_id=item_id).pack()
                )
            )

    builder.row(InlineKeyboardButton(text="✅ Завершить редактирование", callback_data=AdminEditOrder(action="finish", order_id=order_id).pack()))
    return builder.as_markup()