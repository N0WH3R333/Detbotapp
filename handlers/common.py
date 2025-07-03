import logging
import math
from aiogram import F, Router, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery

from keyboards.reply import get_main_menu_keyboard
from keyboards.inline import get_my_bookings_keyboard, CancelBooking, OrderPaginator, get_orders_keyboard, CancelOrder
from database.db import get_user_bookings, cancel_booking_in_db, get_user_orders, cancel_order_in_db, get_product_by_id
from config import WEBAPP_URL, ADMIN_ID
from utils.scheduler import cancel_reminder

ORDERS_PER_PAGE = 5  # Количество заказов на одной странице

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart(), StateFilter(None))
async def cmd_start(message: Message):
    # Мы больше не сбрасываем данные при старте, чтобы они сохранялись
    await message.answer(
        "Привет! 👋\n\n"
        "Я бот для записи в детейлинг-центр.\n\n"
        "Выберите, что вас интересует:",
        reply_markup=get_main_menu_keyboard(webapp_url=WEBAPP_URL)
    )


@router.message(F.text == "📓 Мои записи")
async def show_my_bookings(message: Message):
    logger.debug(f"User {message.from_user.id} requested their bookings.")
    bookings = await get_user_bookings(user_id=message.from_user.id)

    if not bookings:
        await message.answer("У вас пока нет активных записей.")
        return

    response_text = "<b>Ваши активные записи:</b>\n\n"
    for booking in bookings:
        response_text += f"<b>Запись #{booking['id']}</b>\n"
        price_str = f" - {booking['price']} руб." if 'price' in booking else ""
        response_text += f"Услуга: {booking['service']}{price_str}\n"
        response_text += f"Дата и время: {booking['date']} в {booking['time']}\n\n"

    await message.answer(
        response_text,
        reply_markup=get_my_bookings_keyboard(bookings)
    )


@router.callback_query(CancelBooking.filter())
async def cancel_my_booking(callback: CallbackQuery, callback_data: CancelBooking):
    logger.debug(f"User {callback.from_user.id} initiated cancellation for booking_id={callback_data.booking_id}")
    user_id = callback.from_user.id
    booking_id_to_cancel = callback_data.booking_id

    # 1. Удаляем запись из нашей "базы"
    cancelled_booking = await cancel_booking_in_db(user_id=user_id, booking_id=booking_id_to_cancel)

    if not cancelled_booking:
        await callback.answer("Не удалось отменить запись. Возможно, она уже отменена.", show_alert=True)
        return

    # 1.5. Отменяем запланированное напоминание
    await cancel_reminder(booking_id=booking_id_to_cancel)

    # 2. Получаем обновленный список записей
    remaining_bookings = await get_user_bookings(user_id=user_id)

    # 3. Обновляем сообщение
    if not remaining_bookings:
        await callback.message.edit_text("✅ Все ваши записи отменены.")
    else:
        response_text = "<b>Ваши активные записи:</b>\n\n"
        for booking in remaining_bookings:
            response_text += f"<b>Запись #{booking['id']}</b>\n"
            price_str = f" - {booking['price']} руб." if 'price' in booking else ""
            response_text += f"Услуга: {booking['service']}{price_str}\n"
            response_text += f"Дата и время: {booking['date']} в {booking['time']}\n\n"

        await callback.message.edit_text(
            response_text,
            reply_markup=get_my_bookings_keyboard(remaining_bookings)
        )

    await callback.answer(f"Запись #{booking_id_to_cancel} отменена.")
    await callback.message.answer("Вы в главном меню.", reply_markup=get_main_menu_keyboard(webapp_url=WEBAPP_URL))


async def format_orders_page(orders_on_page: list[dict]) -> str:
    """Форматирует текст для одной страницы истории заказов."""
    response_text = "<b>История ваших заказов:</b>\n\n"
    for order in orders_on_page:
        response_text += f"<b>Заказ #{order['id']} от {order['date']}</b>\n"
        response_text += f"<b>Статус:</b> {order.get('status', 'В обработке')}\n"
        shipping_method = order.get("shipping_method", "Не указан")
        delivery_cost = order.get("delivery_cost", 0)
        promocode = order.get("promocode")
        discount_amount = order.get("discount_amount", 0)
        address = order.get("address")
        for item_id, quantity in order['cart'].items():
            product = await get_product_by_id(item_id) or {"name": "Неизвестный товар"}
            response_text += f"  - {product['name']} x {quantity} шт.\n"
        if discount_amount > 0 and promocode:
            response_text += f"<i>Скидка по промокоду '{promocode}': -{discount_amount:.2f} руб.</i>\n"
        response_text += f"<i>Способ получения: {shipping_method}</i>\n"
        if address:
            response_text += f"<i>Адрес: {address}</i>\n"
        if delivery_cost > 0:
            response_text += f"<i>Стоимость доставки: {delivery_cost} руб.</i>\n"
        response_text += f"<i>Итого: {order['total_price']:.2f} руб.</i>\n\n"
    return response_text


@router.message(F.text == "🛍️ Мои заказы")
async def show_my_orders(message: Message):
    logger.debug(f"User {message.from_user.id} requested their orders.")
    user_id = message.from_user.id
    orders = await get_user_orders(user_id=user_id)
    orders.reverse()  # Показываем последние заказы первыми

    if not orders:
        await message.answer("У вас еще нет заказов из магазина.")
        return

    page = 0
    total_pages = math.ceil(len(orders) / ORDERS_PER_PAGE)
    text = await format_orders_page(orders[0:ORDERS_PER_PAGE])

    await message.answer(text, reply_markup=get_orders_keyboard(page=page, total_pages=total_pages, orders_on_page=orders[0:ORDERS_PER_PAGE]))


@router.callback_query(OrderPaginator.filter())
async def paginate_orders(callback: CallbackQuery, callback_data: OrderPaginator):
    page = callback_data.page + 1 if callback_data.action == "next" else callback_data.page - 1

    orders = await get_user_orders(user_id=callback.from_user.id)
    orders.reverse()

    total_pages = math.ceil(len(orders) / ORDERS_PER_PAGE)
    start_index = page * ORDERS_PER_PAGE
    end_index = start_index + ORDERS_PER_PAGE
    text = await format_orders_page(orders[start_index:end_index])

    await callback.message.edit_text(text, reply_markup=get_orders_keyboard(page=page, total_pages=total_pages, orders_on_page=orders[start_index:end_index]))
    await callback.answer()


@router.callback_query(CancelOrder.filter())
async def cancel_my_order(callback: CallbackQuery, callback_data: CancelOrder, bot: Bot):
    """Обрабатывает отмену заказа пользователем."""
    user_id = callback.from_user.id
    order_id_to_cancel = callback_data.order_id

    cancelled_order = await cancel_order_in_db(user_id=user_id, order_id=order_id_to_cancel)

    if not cancelled_order:
        await callback.answer("Не удалось отменить заказ. Возможно, он уже отменен.", show_alert=True)
        return

    # Уведомляем админа
    if ADMIN_ID:
        try:
            user = callback.from_user
            admin_text = (
                f"🚫 <b>Пользователь отменил заказ #{order_id_to_cancel}</b>\n\n"
                f"<b>Клиент:</b> {user.full_name}\n"
                f"<b>ID:</b> <code>{user.id}</code>\n"
                f"<b>Username:</b> @{user.username or 'не указан'}"
            )
            await bot.send_message(ADMIN_ID, admin_text)
        except Exception as e:
            logger.error(f"Failed to send order cancellation notification to admin {ADMIN_ID}. Error: {e}")

    await callback.answer(f"Заказ #{order_id_to_cancel} отменен.", show_alert=False)

    # Обновляем сообщение со списком заказов, возвращаясь на первую страницу
    orders = await get_user_orders(user_id=user_id)
    orders.reverse()

    if not orders:
        await callback.message.edit_text("✅ Заказ отменен. У вас больше нет заказов.")
        return

    page = 0
    total_pages = math.ceil(len(orders) / ORDERS_PER_PAGE)
    orders_on_page = orders[0:ORDERS_PER_PAGE]
    text = await format_orders_page(orders_on_page)

    await callback.message.edit_text(text, reply_markup=get_orders_keyboard(page=page, total_pages=total_pages, orders_on_page=orders_on_page))


@router.message(F.text == "📞 Контакты / Помощь")
async def show_contacts(message: Message):
    contact_text = (
        "<b>Наши контакты:</b>\n\n"
        "📍 <b>Адрес:</b> г. Москва, ул. Автомобильная, д. 1\n"
        "📞 <b>Телефон:</b> <a href='tel:+79991234567'>+7 (999) 123-45-67</a>\n"
        "🕒 <b>Время работы:</b> Ежедневно с 9:00 до 21:00\n\n"
        "Если у вас возникли вопросы или вы хотите обсудить детали заказа, "
        "пожалуйста, свяжитесь с нашим менеджером."
    )
    await message.answer(contact_text, disable_web_page_preview=True)
