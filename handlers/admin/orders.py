import logging
import math

from aiogram import F, Router, Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest

from .states import AdminStates
from database.db import (
    get_all_orders, cancel_order_in_db, update_order_status,
    get_product_by_id, get_all_promocodes, update_order_cart_and_prices
)
from keyboards.admin_inline import (
    get_order_management_keyboard, get_admin_paginator, AdminOrdersPaginator,
    get_back_to_menu_keyboard, get_set_order_status_keyboard, AdminSetOrderStatus,
    get_order_editing_keyboard, AdminEditOrder
)

ADMIN_ITEMS_PER_PAGE = 5
logger = logging.getLogger(__name__)
router = Router()


def _format_admin_orders_list(orders_on_page: list) -> str:
    """Форматирует список заказов для админки."""
    if not orders_on_page:
        return "На этой странице заказов нет."

    text = "<b>Последние заказы:</b>\n\n"
    for order in orders_on_page:
        user_full_name = order.get('user_full_name', f"ID: {order.get('user_id')}")
        user_username = order.get('user_username')
        client_info = f"{user_full_name}"
        if user_username:
            client_info += f" (@{user_username})"

        status = order.get("status", "Неизвестен")
        text += (
            f"<b>Заказ #{order['id']} от {order['date']}</b>\n"
            f"Клиент: {client_info}\n"
            f"Статус: <i>{status}</i>\n"
            f"Сумма: {order['total_price']:.2f} руб.\n---\n"
        )
    return text


async def _recalculate_order_totals(order_data: dict) -> dict:
    """Пересчитывает стоимость заказа на основе его корзины."""
    cart = order_data.get('cart', {})
    items_price = 0
    for item_id, quantity in cart.items():
        product = await get_product_by_id(item_id) or {"price": 0}
        items_price += product["price"] * quantity

    promocode = order_data.get('promocode')
    discount_percent = 0
    if promocode:
        promocodes_db = await get_all_promocodes()
        promo_data = promocodes_db.get(promocode)
        if promo_data and isinstance(promo_data, dict):
            # В админке для пересчета можно не проверять дату/лимит, т.к. промокод уже был применен
            discount_percent = promo_data.get("discount", 0)

    discount_amount = (items_price * discount_percent) / 100
    total_price = items_price - discount_amount + order_data.get('delivery_cost', 0)

    order_data['items_price'] = items_price
    order_data['discount_amount'] = discount_amount
    order_data['total_price'] = total_price
    return order_data


async def _format_order_for_editing(order: dict) -> str:
    """Форматирует текст с деталями заказа для сообщения редактирования."""
    text = f"✏️ <b>Редактирование заказа #{order['id']}</b>\n\n"

    cart = order.get('cart', {})
    if not cart:
        text += "<i>Корзина пуста.</i>\n"
    else:
        text += "<b>Состав:</b>\n"
        for item_id, quantity in cart.items():
            product = await get_product_by_id(item_id) or {}
            product_name = product.get('name', 'Неизвестный товар')
            text += f"  • {product_name}: {quantity} шт.\n"

    text += f"\nСтоимость товаров: {order.get('items_price', 0):.2f} руб."
    text += f"\nСкидка: {order.get('discount_amount', 0):.2f} руб."
    text += f"\nДоставка: {order.get('delivery_cost', 0):.2f} руб."
    text += f"\n<b>Итого: {order.get('total_price', 0):.2f} руб.</b>"

    return text


@router.callback_query(F.data == "admin_order_management")
async def order_management(callback: CallbackQuery):
    """Показывает меню управления заказами."""
    await callback.message.edit_text(
        "Выберите действие с заказами:",
        reply_markup=get_order_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_last_orders")
async def show_last_orders(callback: CallbackQuery):
    """Показывает последние 10 заказов из магазина."""
    all_orders = sorted(await get_all_orders(), key=lambda x: x['id'], reverse=True)

    if not all_orders:
        text = "Заказов из магазина пока нет."
        await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard("admin_order_management"))
        await callback.answer()
        return

    page = 0
    total_pages = math.ceil(len(all_orders) / ADMIN_ITEMS_PER_PAGE)
    orders_on_page = all_orders[0:ADMIN_ITEMS_PER_PAGE]
    text = _format_admin_orders_list(orders_on_page)

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_paginator(
            page=page, total_pages=total_pages,
            paginator_type=AdminOrdersPaginator(action="next", page=0),
            back_callback="admin_order_management"
        )
    )
    await callback.answer()


@router.callback_query(AdminOrdersPaginator.filter())
async def paginate_admin_orders(callback: CallbackQuery, callback_data: AdminOrdersPaginator):
    page = callback_data.page + 1 if callback_data.action == "next" else callback_data.page - 1
    all_orders = sorted(await get_all_orders(), key=lambda x: x['id'], reverse=True)
    total_pages = math.ceil(len(all_orders) / ADMIN_ITEMS_PER_PAGE)
    orders_on_page = all_orders[page * ADMIN_ITEMS_PER_PAGE:(page + 1) * ADMIN_ITEMS_PER_PAGE]
    text = _format_admin_orders_list(orders_on_page)
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_paginator(
            page=page, total_pages=total_pages,
            paginator_type=callback_data,
            back_callback="admin_order_management"
        )
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_order_start")
async def start_cancel_order(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс отмены заказа."""
    await state.set_state(AdminStates.entering_order_id_to_cancel)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID заказа, который нужно отменить:",
        reply_markup=get_back_to_menu_keyboard("admin_order_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_order_id_to_cancel, F.text)
async def process_cancel_order(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ID заказа для отмены."""
    data = await state.get_data()
    message_to_edit_id = data.get("message_to_edit")
    await message.delete()

    try:
        order_id = int(message.text)
        cancelled_order = await cancel_order_in_db(order_id=order_id, user_id=None)

        if cancelled_order:
            client_user_id = cancelled_order.get('user_id')
            if client_user_id:
                try:
                    notification_text = f"❗️ <b>Ваш заказ #{order_id} был отменен администратором.</b>\n\nЕсли у вас есть вопросы, пожалуйста, свяжитесь с нами."
                    await bot.send_message(client_user_id, notification_text)
                    logger.info(f"Sent order cancellation notification to user {client_user_id} for order {order_id}")
                except Exception as e:
                    logger.error(f"Failed to send order cancellation notification to user {client_user_id}. Error: {e}")
            text = f"✅ Заказ с ID <code>{order_id}</code> отменен. Клиент уведомлен."
        else:
            text = f"⚠️ Заказ с ID <code>{order_id}</code> не найден."
    except ValueError:
        text = "⚠️ Неверный формат ID. Пожалуйста, введите число."
    except Exception as e:
        logger.error(f"Error cancelling order by admin: {e}")
        text = "❌ Произошла ошибка при отмене заказа."

    await state.clear()
    if message_to_edit_id:
        await bot.edit_message_text(
            f"{text}\n\nВыберите следующее действие:",
            chat_id=message.chat.id,
            message_id=message_to_edit_id,
            reply_markup=get_order_management_keyboard()
        )


@router.callback_query(F.data == "admin_change_order_status_start")
async def start_change_order_status(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс смены статуса заказа."""
    await state.set_state(AdminStates.entering_order_id_for_status_change)
    await callback.message.edit_text(
        "Введите ID заказа, для которого нужно изменить статус:",
        reply_markup=get_back_to_menu_keyboard("admin_order_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_order_id_for_status_change, F.text)
async def process_order_id_for_status_change(message: Message, state: FSMContext):
    """Получает ID заказа и предлагает выбрать новый статус."""
    await state.clear()
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Неверный формат ID. Пожалуйста, введите число.")
        return

    all_orders = await get_all_orders()
    target_order = next((o for o in all_orders if o.get('id') == order_id), None)

    if not target_order:
        await message.answer(f"Заказ с ID <code>{order_id}</code> не найден.")
        return

    await message.delete()

    text = _format_admin_orders_list([target_order])
    await message.answer(
        f"<b>Текущий заказ:</b>\n\n{text}\nВыберите новый статус:",
        reply_markup=get_set_order_status_keyboard(order_id)
    )


@router.callback_query(AdminSetOrderStatus.filter())
async def set_order_status(callback: CallbackQuery, callback_data: AdminSetOrderStatus, bot: Bot):
    """Устанавливает новый статус и уведомляет клиента."""
    order_id = callback_data.order_id
    status_code = callback_data.status

    status_map = {
        "assembled": "Собран",
        "shipped": "Отправлен"
    }
    new_status_text = status_map.get(status_code, "Неизвестный статус")

    updated_order = await update_order_status(order_id, new_status_text)

    if not updated_order:
        await callback.message.edit_text(f"Не удалось обновить статус для заказа #{order_id}. Возможно, он был удален.")
        return

    client_user_id = updated_order.get('user_id')
    if client_user_id:
        try:
            notification_text = f"ℹ️ Статус вашего заказа <b>#{order_id}</b> изменился на: <b>{new_status_text}</b>"
            await bot.send_message(client_user_id, notification_text)
            logger.info(f"Sent status update to user {client_user_id} for order {order_id}")
        except Exception as e:
            logger.error(f"Failed to send status update to user {client_user_id}. Error: {e}")

    await callback.message.edit_text(f"✅ Статус заказа #{order_id} изменен на '<b>{new_status_text}</b>'. Клиент уведомлен.")
    await callback.answer()


@router.callback_query(F.data == "admin_edit_order_start")
async def start_edit_order(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс редактирования заказа."""
    await state.set_state(AdminStates.editing_order)
    await callback.message.edit_text(
        "Введите ID заказа, который нужно отредактировать:",
        reply_markup=get_back_to_menu_keyboard("admin_order_management")
    )
    await callback.answer()


@router.message(AdminStates.editing_order, F.text)
async def process_order_id_for_editing(message: Message, state: FSMContext):
    """Получает ID заказа и предлагает интерфейс редактирования."""
    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("Неверный формат ID. Пожалуйста, введите число.")
        return

    all_orders = await get_all_orders()
    target_order = next((o for o in all_orders if o.get('id') == order_id), None)

    if not target_order:
        await message.answer(f"Заказ с ID <code>{order_id}</code> не найден.")
        await state.clear()
        return

    await state.update_data(order=target_order)
    await message.delete()

    text = await _format_order_for_editing(target_order)
    await message.answer(
        text,
        reply_markup=await get_order_editing_keyboard(target_order)
    )


@router.callback_query(AdminEditOrder.filter(F.action == "remove_item"), AdminStates.editing_order)
async def remove_item_from_order(callback: CallbackQuery, callback_data: AdminEditOrder, state: FSMContext):
    """Удаляет одну единицу товара из заказа."""
    user_data = await state.get_data()
    order = user_data.get('order')
    item_to_remove = callback_data.item_id

    if not order or not item_to_remove or item_to_remove not in order.get('cart', {}):
        await callback.answer("Ошибка: не удалось найти заказ или товар в нем.", show_alert=True)
        return

    if order['cart'][item_to_remove] > 1:
        order['cart'][item_to_remove] -= 1
    else:
        del order['cart'][item_to_remove]

    order = await _recalculate_order_totals(order)
    await state.update_data(order=order)

    text = await _format_order_for_editing(order)
    await callback.message.edit_text(text, reply_markup=await get_order_editing_keyboard(order))
    await callback.answer("Товар удален.")


@router.callback_query(AdminEditOrder.filter(F.action == "finish"), AdminStates.editing_order)
async def finish_order_editing(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Завершает редактирование, сохраняет изменения и уведомляет клиента."""
    user_data = await state.get_data()
    order = user_data.get('order')

    if not order:
        await callback.answer("Ошибка: не удалось найти данные заказа.", show_alert=True)
        return

    new_prices = {
        'items_price': order.get('items_price'),
        'discount_amount': order.get('discount_amount'),
        'total_price': order.get('total_price')
    }
    updated_order = await update_order_cart_and_prices(order['id'], order['cart'], new_prices)

    await state.clear()

    if not updated_order:
        await callback.message.edit_text("Не удалось сохранить изменения в базе данных.", reply_markup=get_order_management_keyboard())
        return

    client_user_id = updated_order.get('user_id')
    if client_user_id:
        try:
            notification_text = (
                f"⚠️ <b>Внимание!</b> Администратор изменил состав вашего заказа <b>#{order['id']}</b>.\n\n"
                f"Пожалуйста, проверьте актуальный состав и сумму в разделе 'Мои заказы'."
            )
            await bot.send_message(client_user_id, notification_text)
            logger.info(f"Sent order edit notification to user {client_user_id} for order {order['id']}")
        except Exception as e:
            logger.error(f"Failed to send order edit notification to user {client_user_id}. Error: {e}")

    await callback.message.edit_text(
        f"✅ Заказ #{order['id']} успешно изменен. Клиент уведомлен.",
        reply_markup=get_order_management_keyboard()
    )
    await callback.answer()