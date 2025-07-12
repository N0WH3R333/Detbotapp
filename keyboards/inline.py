from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CancelBooking(CallbackData, prefix="cancel_booking"):
    """CallbackData для отмены записи. Содержит ID записи."""
    booking_id: int


class CancelOrder(CallbackData, prefix="cancel_order"):
    order_id: int


class OrderPaginator(CallbackData, prefix="order_page"):
    action: str  # "prev" or "next"
    page: int


def get_services_keyboard(services: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру услуг на основе словаря SERVICES_DB."""
    builder = InlineKeyboardBuilder()
    for service_id, service_data in services.items():
        builder.button(text=f"{service_data['name']} - {service_data['price']} руб.", callback_data=service_id)
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()


def get_time_slots_keyboard(occupancy: dict[str, int], working_hours: list[str], max_bookings: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    has_available_slots = False
    for slot in working_hours:
        count = occupancy.get(slot, 0)
        if count < max_bookings:
            builder.button(text=slot, callback_data=f"time:{slot}")
            has_available_slots = True
        else:
            builder.button(text=f"❌ {slot}", callback_data="ignore")

    if not has_available_slots:
        builder.buttons.clear()
        builder.button(text="На эту дату нет свободных слотов", callback_data="ignore")

    # выстраивает кнопки в два столбца для компактности
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад к выбору даты", callback_data="back_to_calendar"))
    return builder.as_markup()


def get_payment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить и оплатить", callback_data="confirm_payment")
    builder.button(text="❌ Отменить", callback_data="cancel_booking")
    builder.adjust(1)
    return builder.as_markup()


def get_my_bookings_keyboard(bookings: list[dict]) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками отмены для каждой записи."""
    builder = InlineKeyboardBuilder()
    for booking in bookings:
        builder.button(
            text=f"❌ Отменить запись #{booking['id']}",
            callback_data=CancelBooking(booking_id=booking['id']).pack()
        )
    builder.adjust(1)
    return builder.as_markup()


def get_shipping_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора способа доставки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚚 Доставка курьером", callback_data="shipping_delivery")
    builder.button(text="🚶‍♂️ Самовывоз", callback_data="shipping_pickup")
    builder.adjust(1)
    return builder.as_markup()


def get_orders_keyboard(page: int, total_pages: int, orders_on_page: list[dict]) -> InlineKeyboardMarkup:
    """Создает клавиатуру для истории заказов с кнопками отмены и пагинацией."""
    builder = InlineKeyboardBuilder()

    # Добавляем кнопки отмены для каждого заказа на странице
    for order in orders_on_page:
        builder.button(
            text=f"❌ Отменить заказ #{order['id']}",
            callback_data=CancelOrder(order_id=order['id']).pack()
        )
    if orders_on_page:
        builder.adjust(1)

    # Добавляем пагинацию
    pagination_row = []
    if page > 0:
        pagination_row.append(InlineKeyboardButton(text="< Назад", callback_data=OrderPaginator(action="prev", page=page).pack()))

    if total_pages > 1:
        pagination_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="ignore_page_count"))

    if page < total_pages - 1:
        pagination_row.append(InlineKeyboardButton(text="Вперед >", callback_data=OrderPaginator(action="next", page=page).pack()))

    if pagination_row:
        builder.row(*pagination_row)
    return builder.as_markup()