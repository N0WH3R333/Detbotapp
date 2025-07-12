from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import get_product_by_id
from utils.constants import SERVICE_NAMES


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


class AdminClientPaginator(CallbackData, prefix="admin_client_page"):
    action: str
    page: int


class AdminEditOrder(CallbackData, prefix="admin_edit_order"):
    action: str  # 'remove_item', 'finish'
    order_id: int
    item_id: str | None = None # ID товара для удаления


class AdminEditClient(CallbackData, prefix="admin_edit_client"):
    action: str # 'select', 'edit_name'
    user_id: int


class AdminPriceEdit(CallbackData, prefix="admin_price_edit"):
    action: str # 'navigate' or 'edit'
    # path is a colon-separated string like 'polishing:small:light_polishing'
    path: str


class AdminManageCandidate(CallbackData, prefix="adm_candidate"):
    action: str  # view, delete, back_list, get_file
    candidate_id: int
    page: int


class AdminCandidatesPaginator(CallbackData, prefix="adm_cand_pag"):
    action: str  # prev, next, noop
    page: int


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Основная клавиатура админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗓️ Управление записями", callback_data="admin_booking_management")
    builder.button(text="🛍️ Управление заказами", callback_data="admin_order_management")
    builder.button(text="🎁 Управление промокодами", callback_data="admin_promocode_management")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="👤 Управление клиентами", callback_data="admin_client_management")
    builder.button(text="💰 Управление ценами", callback_data="admin_price_management")
    builder.button(text="📬 Рассылка", callback_data="admin_broadcast")
    builder.button(text="🚷 Управление блокировками", callback_data="admin_block_management")
    builder.button(text="📬 Кандидаты", callback_data="admin_candidates_management")
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
    builder.button(text="✨ Для услуг детейлинга", callback_data="admin_add_promo_type_detailing")
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
    builder.row(InlineKeyboardButton(text="🗓️ Управлять выходными днями", callback_data="admin_manage_closed_days"))
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


def get_price_editing_keyboard(price_data: dict, current_path: str = "") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для навигации и редактирования цен.
    price_data: текущий уровень вложенности словаря цен.
    current_path: текущий путь в виде строки 'key1:key2'.
    """
    builder = InlineKeyboardBuilder()

    for key, value in price_data.items():
        # Формируем новый путь для callback_data
        new_path = f"{current_path}|{key}" if current_path else key

        # Получаем читаемое имя для кнопки
        display_name = SERVICE_NAMES.get(key, key.replace('_', ' ').capitalize())

        if isinstance(value, dict):
            # Если значение - словарь, это навигационная кнопка
            builder.button(
                text=f"➡️ {display_name}",
                callback_data=AdminPriceEdit(action="navigate", path=new_path).pack()
            )
        elif isinstance(value, (int, float)):
            # Если значение - число, это кнопка для редактирования цены
            builder.button(
                text=f"✏️ {display_name}: {value} руб.",
                callback_data=AdminPriceEdit(action="edit", path=new_path).pack()
            )

    # Кнопка "Назад"
    if current_path:
        parent_path = "|".join(current_path.split('|')[:-1])
        builder.row(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=AdminPriceEdit(action="navigate", path=parent_path).pack()
        ))
    else:
        # Если мы в корне, возвращаемся в главное меню админки
        builder.row(InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_back_to_main"))

    builder.adjust(1)
    return builder.as_markup()


def get_clients_list_keyboard(clients_on_page: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком клиентов для управления."""
    builder = InlineKeyboardBuilder()
    for client in clients_on_page:
        user_id = client['user_id']
        name = client.get('user_full_name', f"ID: {user_id}")
        username = client.get('user_username')
        display_name = f"{name}" + (f" (@{username})" if username else "")

        builder.row(
            InlineKeyboardButton(text=display_name, callback_data="ignore"),
            InlineKeyboardButton(
                text="✏️ Изменить",
                callback_data=AdminEditClient(action="select", user_id=user_id).pack()
            )
        )

    # Paginator
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton(text="< Назад", callback_data=AdminClientPaginator(action="prev", page=page).pack()))
    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        pagination_row.append(InlineKeyboardButton(text="Вперед >", callback_data=AdminClientPaginator(action="next", page=page).pack()))

    if pagination_row:
        builder.row(*pagination_row)

    builder.row(InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_back_to_main"))
    return builder.as_markup()


def get_client_editing_keyboard(user_id: int, user_full_name: str, back_callback: str) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования данных клиента."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✏️ Изменить имя ({user_full_name})", callback_data=AdminEditClient(action="edit_name", user_id=user_id).pack())
    builder.button(text="⬅️ Назад к списку клиентов", callback_data=back_callback)
    builder.adjust(1)
    return builder.as_markup()


def get_candidates_list_keyboard(candidates_on_page: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком кандидатов и пагинацией.
    """
    builder = InlineKeyboardBuilder()
    for candidate in candidates_on_page:
        builder.button(
            text=f"Отклик #{candidate['id']} от {candidate['user_full_name']}",
            callback_data=AdminManageCandidate(action="view", candidate_id=candidate['id'], page=page).pack()
        )
    builder.adjust(1)

    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=AdminCandidatesPaginator(action="prev", page=page).pack())
        )
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton(text="➡️", callback_data=AdminCandidatesPaginator(action="next", page=page).pack())
        )
    if pagination_row:
        builder.row(*pagination_row)

    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_back_to_main"))
    return builder.as_markup()