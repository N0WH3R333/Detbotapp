import asyncio
import logging
from datetime import datetime, timedelta
from collections import Counter
import math
import io
import csv
import json
from babel.dates import format_date

from aiogram import F, Router, Bot, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_ID
# Предполагаем, что cancel_booking_in_db может работать только с booking_id
from database.db import (
    get_all_bookings, get_all_orders, block_user, unblock_user,
    get_blocked_users, cancel_booking_in_db, cancel_order_in_db, get_all_unique_user_ids, update_order_status,
    update_order_cart_and_prices, get_all_promocodes, add_promocode_to_db, get_product_by_id
)
from keyboards.admin_inline import (
    get_admin_keyboard, get_block_management_keyboard,
    get_booking_management_keyboard, get_back_to_menu_keyboard,
    get_stats_menu_keyboard, get_order_management_keyboard,
    get_broadcast_confirmation_keyboard, AdminOrdersPaginator, AdminBookingsPaginator, get_admin_paginator,
    AdminSetOrderStatus, get_set_order_status_keyboard, AdminEditOrder, get_order_editing_keyboard,
    get_promocode_management_keyboard, get_promocode_type_keyboard
)
from utils.scheduler import cancel_reminder
from keyboards.calendar import create_stats_calendar, StatsCalendarCallback
from utils.reports import generate_period_report_text

# Для построения графиков. Не забудьте установить: pip install matplotlib
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

ADMIN_ITEMS_PER_PAGE = 5  # Количество элементов на странице в админке

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    entering_user_id_to_block = State()
    entering_user_id_to_unblock = State()
    entering_booking_id_to_cancel = State()
    entering_order_id_to_cancel = State()
    entering_broadcast_message = State()
    confirming_broadcast = State()
    choosing_stats_start_date = State()
    choosing_stats_end_date = State()
    entering_promocode_code = State()
    entering_promocode_discount = State()
    choosing_promocode_start_date = State()
    choosing_promocode_end_date = State()
    entering_promocode_limit = State()
    entering_order_id_for_status_change = State()
    editing_order = State()

# Этот фильтр будет пропускать только администратора
try:
    # Пытаемся преобразовать ADMIN_ID в число.
    # Если переменная не задана или имеет неверный формат, фильтр не будет применен.
    admin_id_int = int(ADMIN_ID)
    router.message.filter(F.from_user.id == admin_id_int)
    router.callback_query.filter(F.from_user.id == admin_id_int)
    logger.info(f"Admin filter enabled for user ID: {admin_id_int}")
except (ValueError, TypeError):
    logger.warning("ADMIN_ID is not set or has an invalid format. Admin commands will be disabled.")
    

# --- Вспомогательные функции ---

async def _get_filtered_bookings(period: str) -> tuple[list, str]:
    """Возвращает отфильтрованный и отсортированный список записей и заголовок."""
    all_bookings = await get_all_bookings()
    now = datetime.now()
    filtered_bookings = []
    title = ""

    if period == "today":
        today_str = now.strftime("%d.%m.%Y")
        filtered_bookings = [b for b in all_bookings if b['date'] == today_str]
        title = f"Записи на сегодня ({today_str})"
    elif period == "week":
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        title = f"Записи на неделю ({start_of_week.strftime('%d.%m')} - {end_of_week.strftime('%d.%m')})"
        for booking in all_bookings:
            try:
                booking_date = datetime.strptime(booking['date'], "%d.%m.%Y")
                if start_of_week.date() <= booking_date.date() <= end_of_week.date():
                    filtered_bookings.append(booking)
            except (ValueError, KeyError):
                continue
    elif period == "month":
        title = f"Записи на {format_date(now, 'LLLL yyyy г.', locale='ru_RU')}"
        for booking in all_bookings:
            try:
                booking_date = datetime.strptime(booking['date'], "%d.%m.%Y")
                if booking_date.month == now.month and booking_date.year == now.year:
                    filtered_bookings.append(booking)
            except (ValueError, KeyError):
                continue

    # Сортируем по дате и времени
    sorted_bookings = sorted(
        filtered_bookings,
        key=lambda x: (datetime.strptime(x['date'], "%d.%m.%Y"), x['time'])
    )
    return sorted_bookings, title


async def _format_bookings_list(bookings: list, title: str) -> str:
    """Форматирует список записей для вывода."""
    if not bookings:
        return f"<b>{title}</b>\n\nЗаписей в этом периоде нет."

    response_text = f"<b>{title}:</b>\n\n"
    for booking in bookings:
        user_full_name = booking.get('user_full_name', f"ID: {booking.get('user_id')}")
        user_username = booking.get('user_username')
        client_info = f"{user_full_name}"
        if user_username:
            client_info += f" (@{user_username})"

        response_text += (
            f"<b>ID: {booking['id']}</b> | {booking['date']} в {booking['time']}\n"
            f"Услуга: {booking['service']}\n"
            f"Клиент: {client_info}\n---\n"
        )
    return response_text


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


def _generate_bar_chart(data: Counter, title: str, xlabel: str, ylabel: str) -> io.BytesIO | None:
    """Генерирует bar chart из объекта Counter и возвращает его в виде байтов."""
    if not data or plt is None:
        return None

    labels, values = zip(*data.most_common())

    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, max(6, len(labels) * 0.5)))

    bars = ax.barh(labels, values, color='skyblue')
    ax.set_title(title, fontsize=16, pad=20)
    ax.set_xlabel(ylabel, fontsize=12)
    ax.set_ylabel(xlabel, fontsize=12)
    ax.invert_yaxis()  # Показать самый популярный элемент сверху

    # Добавляем значения на бары
    for bar in bars:
        ax.text(bar.get_width() + (max(values) * 0.01), bar.get_y() + bar.get_height()/2, f'{bar.get_width()}', va='center')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return buf


async def _process_fsm_input_and_edit(
    message: Message, state: FSMContext, bot: Bot,
    processing_func, success_markup
):
    """Универсальный обработчик для FSM: удаляет сообщение, обрабатывает, редактирует исходное."""
    data = await state.get_data()
    message_to_edit_id = data.get("message_to_edit")

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except TelegramBadRequest:
        logger.warning(f"Could not delete user message {message.message_id}")

    text = await processing_func(message.text)

    await state.clear()
    final_text = f"{text}\n\nВыберите следующее действие:"

    if message_to_edit_id:
        try:
            await bot.edit_message_text(
                text=final_text,
                chat_id=message.chat.id,
                message_id=message_to_edit_id,
                reply_markup=success_markup
            )
        except TelegramBadRequest:
            # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое
            await bot.send_message(message.chat.id, final_text, reply_markup=success_markup)
    else:
        await bot.send_message(message.chat.id, final_text, reply_markup=success_markup)


# --- Главное меню и навигация ---

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Открывает админ-панель."""
    await state.clear()
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext):
    """Возвращает в главное меню админки, редактируя сообщение."""
    await state.clear()
    await callback.message.edit_text(
        "Добро пожаловать в админ-панель!",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


# --- Управление записями ---

@router.callback_query(F.data == "admin_booking_management")
async def booking_management(callback: CallbackQuery):
    """Показывает меню управления записями."""
    await callback.message.edit_text(
        "Выберите период для просмотра записей или действие:",
        reply_markup=get_booking_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bookings_"))
async def show_bookings_period(callback: CallbackQuery):
    """Показывает записи за выбранный период (сегодня, неделя, месяц)."""
    period = callback.data.split("_")[-1]
    filtered_bookings, title = await _get_filtered_bookings(period)

    if not filtered_bookings:
        response_text = await _format_bookings_list(filtered_bookings, title)
        await callback.message.edit_text(
            response_text,
            reply_markup=get_back_to_menu_keyboard("admin_booking_management")
        )
        await callback.answer()
        return

    page = 0
    total_pages = math.ceil(len(filtered_bookings) / ADMIN_ITEMS_PER_PAGE)
    bookings_on_page = filtered_bookings[0:ADMIN_ITEMS_PER_PAGE]

    response_text = await _format_bookings_list(bookings_on_page, title)

    await callback.message.edit_text(
        response_text,
        reply_markup=get_admin_paginator(
            page=page, total_pages=total_pages,
            paginator_type=AdminBookingsPaginator(action="next", page=0, period=period),
            back_callback="admin_booking_management"
        )
    )
    await callback.answer()


@router.callback_query(AdminBookingsPaginator.filter())
async def paginate_admin_bookings(callback: CallbackQuery, callback_data: AdminBookingsPaginator):
    page = callback_data.page + 1 if callback_data.action == "next" else callback_data.page - 1
    period = callback_data.period
    filtered_bookings, title = await _get_filtered_bookings(period)
    total_pages = math.ceil(len(filtered_bookings) / ADMIN_ITEMS_PER_PAGE)
    bookings_on_page = filtered_bookings[page * ADMIN_ITEMS_PER_PAGE:(page + 1) * ADMIN_ITEMS_PER_PAGE]
    response_text = await _format_bookings_list(bookings_on_page, title)
    await callback.message.edit_text(
        response_text,
        reply_markup=get_admin_paginator(
            page=page, total_pages=total_pages,
            paginator_type=callback_data,
            back_callback="admin_booking_management"
        )
    )
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_booking_start")
async def start_cancel_booking(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс отмены записи."""
    await state.set_state(AdminStates.entering_booking_id_to_cancel)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID записи, которую нужно отменить:",
        reply_markup=get_back_to_menu_keyboard("admin_booking_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_booking_id_to_cancel, F.text)
async def process_cancel_booking(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ID записи для отмены."""
    async def _processor(text: str):
        try:
            booking_id = int(text)
            # Админ может отменять любую запись, поэтому user_id=None
            cancelled_booking = await cancel_booking_in_db(booking_id=booking_id, user_id=None)

            if cancelled_booking:
                # Отменяем напоминание
                await cancel_reminder(booking_id=booking_id)

                # Попытка уведомить клиента
                client_user_id = cancelled_booking.get('user_id')
                if client_user_id:
                    try:
                        notification_text = (
                            f"❗️ <b>Ваша запись была отменена администратором.</b>\n\n"
                            f"<b>Детали отмененной записи:</b>\n"
                            f"Услуга: {cancelled_booking.get('service', 'не указана')}\n"
                            f"Дата: {cancelled_booking.get('date', 'не указана')}\n"
                            f"Время: {cancelled_booking.get('time', 'не указано')}\n\n"
                            f"Для уточнения деталей или создания новой записи, пожалуйста, вернитесь в главное меню."
                        )
                        await bot.send_message(client_user_id, notification_text)
                        logger.info(f"Sent cancellation notification to user {client_user_id} for booking {booking_id}")
                    except Exception as e:
                        logger.error(f"Failed to send cancellation notification to user {client_user_id}. Error: {e}")

                return f"✅ Запись с ID <code>{booking_id}</code> отменена. Клиент уведомлен."
            else:
                return f"⚠️ Запись с ID <code>{booking_id}</code> не найдена."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error cancelling booking by admin: {e}")
            return "❌ Произошла ошибка при отмене записи."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_booking_management_keyboard()
    )


# --- Управление блокировками ---

@router.callback_query(F.data == "admin_block_management")
async def block_management(callback: CallbackQuery):
    """Показывает меню управления блокировками."""
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=get_block_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_block_user")
async def start_blocking_user(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс блокировки пользователя."""
    await state.set_state(AdminStates.entering_user_id_to_block)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID пользователя для блокировки:",
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_user_id_to_block, F.text)
async def process_blocking_user(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает введенный ID для блокировки."""
    async def _processor(text: str):
        try:
            user_id = int(text)
            await block_user(user_id)
            return f"✅ Пользователь <code>{user_id}</code> заблокирован."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error blocking user: {e}")
            return "❌ Произошла ошибка при блокировке."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_block_management_keyboard()
    )


@router.callback_query(F.data == "admin_unblock_user")
async def start_unblocking_user(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс разблокировки пользователя."""
    await state.set_state(AdminStates.entering_user_id_to_unblock)
    await state.update_data(message_to_edit=callback.message.message_id)
    await callback.message.edit_text(
        "Введите ID пользователя для разблокировки:",
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()


@router.message(AdminStates.entering_user_id_to_unblock, F.text)
async def process_unblocking_user(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает введенный ID для разблокировки."""
    async def _processor(text: str):
        try:
            user_id = int(text)
            await unblock_user(user_id)
            return f"✅ Пользователь <code>{user_id}</code> разблокирован."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")
            return "❌ Произошла ошибка при разблокировке."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_block_management_keyboard()
    )


@router.callback_query(F.data == "admin_show_blocked")
async def show_blocked_users(callback: CallbackQuery):
    """Показывает список заблокированных пользователей."""
    blocked_users = await get_blocked_users()
    if not blocked_users:
        text = "Список заблокированных пользователей пуст."
    else:
        text = "<b>Заблокированные пользователи:</b>\n\n"
        text += "\n".join(f"• <code>{user_id}</code>" for user_id in blocked_users)

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_menu_keyboard("admin_block_management")
    )
    await callback.answer()


# --- Управление заказами ---

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
    async def _processor(text: str):
        try:
            order_id = int(text)
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
                return f"✅ Заказ с ID <code>{order_id}</code> отменен. Клиент уведомлен."
            else:
                return f"⚠️ Заказ с ID <code>{order_id}</code> не найден."
        except ValueError:
            return "⚠️ Неверный формат ID. Пожалуйста, введите число."
        except Exception as e:
            logger.error(f"Error cancelling order by admin: {e}")
            return "❌ Произошла ошибка при отмене заказа."

    await _process_fsm_input_and_edit(
        message, state, bot, _processor, get_order_management_keyboard()
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

    # Удаляем сообщение пользователя с ID
    await message.delete()

    # Показываем инфо о заказе и кнопки для смены статуса
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

    # Уведомляем клиента
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

# --- Управление промокодами ---

@router.callback_query(F.data == "admin_promocode_management")
async def promocode_management(callback: CallbackQuery):
    """Показывает меню управления промокодами."""
    await callback.message.edit_text(
        "Здесь вы можете добавлять и просматривать промокоды для магазина.",
        reply_markup=get_promocode_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_show_promocodes")
async def show_all_promocodes(callback: CallbackQuery):
    """Показывает список всех действующих промокодов."""
    promocodes = await get_all_promocodes()
    today = datetime.now().date()

    if not promocodes:
        text = "На данный момент нет ни одного промокода."
    else:
        text = "<b>Действующие промокоды:</b>\n\n"
        for code, data in promocodes.items():
            try:
                start_date = datetime.strptime(data.get("start_date"), "%Y-%m-%d").date()
                end_date = datetime.strptime(data.get("end_date"), "%Y-%m-%d").date()
                status_icon = "✅" if start_date <= today <= end_date else "❌"
                date_range = f"({start_date.strftime('%d.%m.%y')} - {end_date.strftime('%d.%m.%y')})"
            except (ValueError, KeyError, TypeError):
                status_icon = "⚠️"
                date_range = "(неверный формат дат)"

            usage_text = ""
            limit = data.get("usage_limit")
            if limit is not None:
                used = data.get("times_used", 0)
                usage_text = f"({used}/{limit})"
            else:
                usage_text = f"({data.get('times_used', 0)}/∞)"

            text += f"{status_icon} <code>{code}</code> - {data.get('discount', '?')}% {date_range} {usage_text}\n"

    await callback.message.edit_text(text, reply_markup=get_back_to_menu_keyboard("admin_promocode_management"))
    await callback.answer()


@router.callback_query(F.data == "admin_add_promocode_start")
async def add_promocode_start(callback: CallbackQuery):
    """Спрашивает тип промокода."""
    await callback.message.edit_text(
        "Выберите, для какого раздела вы хотите создать промокод:",
        reply_markup=get_promocode_type_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_promo_type_detailing")
async def add_promo_type_detailing(callback: CallbackQuery):
    """Заглушка для промокодов на детейлинг."""
    await callback.answer("Этот функционал находится в разработке.", show_alert=True)


@router.callback_query(F.data == "admin_add_promo_type_shop")
async def add_promo_type_shop(callback: CallbackQuery, state: FSMContext):
    """Начинает FSM для добавления промокода для магазина."""
    await state.set_state(AdminStates.entering_promocode_code)
    await callback.message.edit_text("Введите сам промокод (например, `SALE25`):")
    await callback.answer()


@router.message(AdminStates.entering_promocode_code, F.text)
async def process_promocode_code(message: Message, state: FSMContext):
    """Сохраняет код промокода и запрашивает скидку."""
    await state.update_data(promocode_code=message.text.upper())
    await state.set_state(AdminStates.entering_promocode_discount)
    await message.answer("Отлично. Теперь введите размер скидки в процентах (только число, например `25`):")


@router.message(AdminStates.entering_promocode_discount, F.text)
async def process_promocode_discount(message: Message, state: FSMContext):
    """Сохраняет скидку и запрашивает начальную дату."""
    try:
        discount = int(message.text)
        await state.update_data(promocode_discount=discount)
        await state.set_state(AdminStates.choosing_promocode_start_date)
        await message.answer(
            "Скидка сохранена. Теперь выберите <b>начальную</b> дату действия промокода:",
            reply_markup=create_stats_calendar()
        )
    except (ValueError, TypeError):
        await message.answer("⚠️ Неверный формат. Пожалуйста, введите только число.")


@router.callback_query(StatsCalendarCallback.filter(), AdminStates.choosing_promocode_start_date)
async def process_promocode_start_date(callback: CallbackQuery, callback_data: StatsCalendarCallback, state: FSMContext):
    """Обрабатывает выбор начальной даты и запрашивает конечную."""
    start_date = datetime(year=callback_data.year, month=callback_data.month, day=callback_data.day)
    await state.update_data(promocode_start_date=start_date.strftime("%Y-%m-%d"))
    await state.set_state(AdminStates.choosing_promocode_end_date)
    await callback.message.edit_text(
        f"Начальная дата: <b>{start_date.strftime('%d.%m.%Y')}</b>\n\n"
        "Теперь выберите <b>конечную</b> дату:",
        reply_markup=create_stats_calendar(year=callback_data.year, month=callback_data.month)
    )
    await callback.answer()


@router.callback_query(StatsCalendarCallback.filter(), AdminStates.choosing_promocode_end_date)
async def process_promocode_end_date(callback: CallbackQuery, callback_data: StatsCalendarCallback, state: FSMContext):
    """Обрабатывает выбор конечной даты и запрашивает лимит."""
    end_date = datetime(year=callback_data.year, month=callback_data.month, day=callback_data.day)
    user_data = await state.get_data()
    start_date = datetime.strptime(user_data.get("promocode_start_date"), "%Y-%m-%d")

    if start_date > end_date:
        await callback.answer("Конечная дата не может быть раньше начальной!", show_alert=True)
        return

    await state.update_data(promocode_end_date=end_date.strftime("%Y-%m-%d"))
    await state.set_state(AdminStates.entering_promocode_limit)
    await callback.message.edit_text(
        f"Начальная дата: <b>{start_date.strftime('%d.%m.%Y')}</b>\n"
        f"Конечная дата: <b>{end_date.strftime('%d.%m.%Y')}</b>\n\n"
        "Теперь введите лимит использований (число). Отправьте 0 для неограниченного количества.",
    )
    await callback.answer()


@router.message(AdminStates.entering_promocode_limit, F.text)
async def process_promocode_limit(message: Message, state: FSMContext):
    """Обрабатывает лимит, сохраняет промокод и завершает FSM."""
    try:
        limit_input = int(message.text)
        # 0 или отрицательное число будет означать "без лимита" (None)
        usage_limit = limit_input if limit_input > 0 else None
        
        user_data = await state.get_data()
        code = user_data.get("promocode_code")
        discount = user_data.get("promocode_discount")
        start_date_str = user_data.get("promocode_start_date")
        end_date_str = user_data.get("promocode_end_date")

        await add_promocode_to_db(code, discount, start_date_str, end_date_str, usage_limit)
        await state.clear()

        limit_text = f"Лимит: {usage_limit} раз" if usage_limit is not None else "Лимит: не ограничен"
        
        await message.answer(
            f"✅ Промокод <code>{code}</code> ({discount}%) успешно добавлен!\n"
            f"Срок действия: с {datetime.strptime(start_date_str, '%Y-%m-%d').strftime('%d.%m.%Y')} по {datetime.strptime(end_date_str, '%Y-%m-%d').strftime('%d.%m.%Y')}\n"
            f"{limit_text}",
            reply_markup=get_promocode_management_keyboard()
        )

    except (ValueError, TypeError):
        await message.answer("⚠️ Неверный формат. Пожалуйста, введите только число.")

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

    # Сохраняем заказ в FSM для последующих манипуляций
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

    # Уменьшаем количество или удаляем товар
    if order['cart'][item_to_remove] > 1:
        order['cart'][item_to_remove] -= 1
    else:
        del order['cart'][item_to_remove]

    # Пересчитываем стоимость
    order = await _recalculate_order_totals(order)

    # Обновляем данные в FSM
    await state.update_data(order=order)

    # Обновляем сообщение
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

    # Сохраняем изменения в БД
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

    # Уведомляем клиента
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

# --- Рассылка ---

@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания рассылки."""
    await state.set_state(AdminStates.entering_broadcast_message)
    await callback.message.edit_text(
        "Перешлите или отправьте сообщение, которое вы хотите разослать всем пользователям.",
        reply_markup=get_back_to_menu_keyboard("admin_back_to_main")
    )
    await callback.answer()


@router.message(AdminStates.entering_broadcast_message)
async def broadcast_message_received(message: Message, state: FSMContext):
    """Получает сообщение (любого типа) для рассылки и просит подтверждения."""
    await state.update_data(broadcast_chat_id=message.chat.id, broadcast_message_id=message.message_id)
    await message.answer(
        "Вы уверены, что хотите отправить это сообщение всем пользователям?",
        reply_markup=get_broadcast_confirmation_keyboard()
    )
    await state.set_state(AdminStates.confirming_broadcast)


@router.callback_query(AdminStates.confirming_broadcast, F.data == "admin_broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждает и запускает рассылку."""
    data = await state.get_data()
    chat_id = data.get('broadcast_chat_id')
    message_id = data.get('broadcast_message_id')
    await state.clear()

    if not chat_id or not message_id:
        await callback.message.edit_text("Произошла ошибка, данные для рассылки утеряны. Попробуйте снова.", reply_markup=get_admin_keyboard())
        return

    user_ids = await get_all_unique_user_ids()

    if not user_ids:
        await callback.message.edit_text("Не найдено ни одного пользователя для рассылки.", reply_markup=get_admin_keyboard())
        return

    await callback.message.edit_text(f"Начинаю рассылку для {len(user_ids)} пользователей...")
    success_count, fail_count = 0, 0
    for user_id in user_ids:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
            success_count += 1
            logger.info(f"Broadcast message sent to {user_id}")
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send broadcast message to {user_id}. Error: {e}")
        await asyncio.sleep(0.1)  # Защита от лимитов Telegram

    report_text = f"✅ <b>Рассылка завершена!</b>\n\nУспешно отправлено: {success_count}\nНе удалось отправить: {fail_count}"
    await callback.message.edit_text(report_text, reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отменяет рассылку."""
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.", reply_markup=get_admin_keyboard())
    await callback.answer()

# --- Статистика ---

@router.callback_query(F.data == "admin_stats")
async def show_stats_menu(callback: CallbackQuery):
    """Показывает меню выбора статистики."""
    await callback.message.edit_text(
        "Выберите, какую статистику вы хотите посмотреть:",
        reply_markup=get_stats_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats_bookings")
async def show_bookings_stats(callback: CallbackQuery):
    """Показывает статистику по записям."""
    all_bookings = await get_all_bookings()

    if not all_bookings:
        text = "Пока нет ни одной записи для анализа."
    else:
        total_bookings = len(all_bookings)
        service_counts = Counter(b.get('service', 'Не указана') for b in all_bookings)

        text = f"📊 <b>Статистика по записям (всего {total_bookings}):</b>\n\n"
        text += "<b>Популярность услуг:</b>\n"
        # Сортируем по популярности
        for service, count in service_counts.most_common():
            text += f"  • {service}: {count} раз(а)\n"

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_menu_keyboard("admin_stats")
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats_shop")
async def show_shop_stats(callback: CallbackQuery):
    """Показывает статистику по магазину."""
    all_orders = await get_all_orders()

    if not all_orders:
        text = "Пока нет ни одного заказа для анализа."
    else:
        total_orders = len(all_orders)
        total_revenue = sum(o.get('total_price', 0) for o in all_orders)
        avg_check = total_revenue / total_orders if total_orders > 0 else 0

        promocode_counts = Counter(o.get('promocode') for o in all_orders if o.get('promocode'))

        text = f"🛒 <b>Статистика по магазину:</b>\n\n"
        text += f"Всего заказов: <b>{total_orders}</b>\n"
        text += f"Общая выручка: <b>{total_revenue:.2f} руб.</b>\n"
        text += f"Средний чек: <b>{avg_check:.2f} руб.</b>\n\n"

        if promocode_counts:
            text += "<b>Использование промокодов:</b>\n"
            for code, count in promocode_counts.most_common():
                text += f"  • '{code}': {count} раз(а)\n"

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_menu_keyboard("admin_stats")
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats_custom_period")
async def start_custom_period_stats(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс получения статистики за произвольный период."""
    await state.set_state(AdminStates.choosing_stats_start_date)
    await callback.message.edit_text(
        "Выберите <b>начальную</b> дату для отчета:",
        reply_markup=create_stats_calendar()
    )
    await callback.answer()


@router.callback_query(StatsCalendarCallback.filter(F.action.in_(["prev-month", "next-month"])), AdminStates.choosing_stats_start_date)
@router.callback_query(StatsCalendarCallback.filter(F.action.in_(["prev-month", "next-month"])), AdminStates.choosing_stats_end_date)
async def stats_calendar_navigate(callback: CallbackQuery, callback_data: StatsCalendarCallback):
    """Обрабатывает навигацию по календарю статистики."""
    year, month = callback_data.year, callback_data.month

    if callback_data.action == "prev-month":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    else:  # "next-month"
        month += 1
        if month == 13:
            month = 1
            year += 1

    await callback.message.edit_reply_markup(reply_markup=create_stats_calendar(year=year, month=month))
    await callback.answer()


@router.callback_query(StatsCalendarCallback.filter(F.action == "select-day"), AdminStates.choosing_stats_start_date)
async def select_stats_start_date(callback: CallbackQuery, callback_data: StatsCalendarCallback, state: FSMContext):
    """Обрабатывает выбор начальной даты."""
    start_date = datetime(year=callback_data.year, month=callback_data.month, day=callback_data.day)
    await state.update_data(start_date=start_date)
    await state.set_state(AdminStates.choosing_stats_end_date)
    await callback.message.edit_text(
        f"Начальная дата: <b>{start_date.strftime('%d.%m.%Y')}</b>\n\n"
        "Теперь выберите <b>конечную</b> дату для отчета:",
        reply_markup=create_stats_calendar(year=callback_data.year, month=callback_data.month)
    )
    await callback.answer()


@router.callback_query(StatsCalendarCallback.filter(F.action == "select-day"), AdminStates.choosing_stats_end_date)
async def select_stats_end_date(callback: CallbackQuery, callback_data: StatsCalendarCallback, state: FSMContext):
    """Обрабатывает выбор конечной даты и формирует отчет."""
    user_data = await state.get_data()
    start_date = user_data.get('start_date')
    end_date = datetime(year=callback_data.year, month=callback_data.month, day=callback_data.day).replace(hour=23, minute=59, second=59)

    if not start_date:
        await callback.message.edit_text("Произошла ошибка. Пожалуйста, начните заново.", reply_markup=get_stats_menu_keyboard())
        await state.clear()
        await callback.answer()
        return

    if start_date > end_date:
        await callback.answer("Конечная дата не может быть раньше начальной!", show_alert=True)
        return

    await callback.message.edit_text("⏳ Формирую отчет...")
    report_text = await generate_period_report_text(start_date, end_date)
    await callback.message.edit_text(report_text, reply_markup=get_stats_menu_keyboard())
    await state.clear()


@router.callback_query(F.data == "admin_chart_bookings")
async def show_bookings_stats_chart(callback: CallbackQuery, bot: Bot):
    """Отправляет график со статистикой по записям."""
    if plt is None:
        await callback.answer("Библиотека для построения графиков (matplotlib) не установлена.", show_alert=True)
        return

    await callback.answer("⏳ Создаю график...")
    all_bookings = await get_all_bookings()
    service_counts = Counter(b.get('service', 'Не указана') for b in all_bookings)

    chart_buffer = _generate_bar_chart(
        data=service_counts,
        title="Популярность услуг",
        xlabel="Услуга",
        ylabel="Количество записей"
    )

    if chart_buffer:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=types.BufferedInputFile(chart_buffer.read(), filename="bookings_stats.png"),
            caption="Статистика по популярности услуг."
        )
    else:
        await callback.message.answer("Нет данных для построения графика.")


@router.callback_query(F.data == "admin_chart_shop")
async def show_shop_stats_chart(callback: CallbackQuery, bot: Bot):
    """Отправляет график со статистикой по промокодам."""
    if plt is None:
        await callback.answer("Библиотека для построения графиков (matplotlib) не установлена.", show_alert=True)
        return

    await callback.answer("⏳ Создаю график...")
    all_orders = await get_all_orders()
    promocode_counts = Counter(o.get('promocode') for o in all_orders if o.get('promocode'))

    chart_buffer = _generate_bar_chart(
        data=promocode_counts,
        title="Использование промокодов",
        xlabel="Промокод",
        ylabel="Количество использований"
    )

    if chart_buffer:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=types.BufferedInputFile(chart_buffer.read(), filename="promocodes_stats.png"),
            caption="Статистика по использованию промокодов."
        )
    else:
        await callback.message.answer("Промокоды еще не использовались.")


@router.callback_query(F.data == "admin_export_bookings_csv")
async def export_bookings_csv(callback: CallbackQuery, bot: Bot):
    """Экспортирует все записи в CSV файл."""
    await callback.answer("⏳ Готовлю файл...")
    all_bookings = await get_all_bookings()
    if not all_bookings:
        await callback.message.answer("Нет записей для экспорта.")
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_bookings[0].keys())
    writer.writeheader()
    writer.writerows(all_bookings)
    output.seek(0)

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=types.BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="all_bookings.csv"),
        caption="Экспорт всех записей."
    )


@router.callback_query(F.data == "admin_export_orders_csv")
async def export_orders_csv(callback: CallbackQuery, bot: Bot):
    """Экспортирует все заказы в CSV файл."""
    await callback.answer("⏳ Готовлю файл...")
    all_orders = await get_all_orders()
    if not all_orders:
        await callback.message.answer("Нет заказов для экспорта.")
        return

    # Преобразуем вложенный словарь 'cart' в строку JSON для совместимости с CSV
    export_data = []
    for order in all_orders:
        order_copy = order.copy()
        order_copy['cart'] = json.dumps(order_copy.get('cart', {}), ensure_ascii=False)
        export_data.append(order_copy)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
    writer.writeheader()
    writer.writerows(export_data)
    output.seek(0)

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=types.BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="all_orders.csv"),
        caption="Экспорт всех заказов."
    )
