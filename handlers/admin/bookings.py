import logging
import math
from datetime import datetime, timedelta, date
from babel.dates import format_date

from aiogram import F, Router, Bot, types
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InputMediaPhoto, InputMediaVideo

from database.db import (
    get_all_bookings, cancel_booking_in_db, get_blocked_dates, get_booking_by_id,
    add_blocked_date, remove_blocked_date
)
from keyboards.admin_inline import (
    get_booking_management_keyboard, get_back_to_menu_keyboard, AdminBookingsPaginator
)
from keyboards.calendar import create_admin_day_management_calendar, StatsCalendarCallback
from utils.scheduler import cancel_reminder
from .info_cmds import format_booking_details_for_admin
from .states import AdminStates

ADMIN_ITEMS_PER_PAGE = 5
logger = logging.getLogger(__name__)
router = Router()

class AdminCancelBooking(CallbackData, prefix="adm_cancel_booking"):
    booking_id: int
    page: int
    period: str

class AdminBookingDetails(CallbackData, prefix="adm_b_details"):
    booking_id: int
    page: int
    period: str


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

    sorted_bookings = sorted(
        filtered_bookings,
        key=lambda x: (datetime.strptime(x['date'], "%d.%m.%Y"), x['time'])
    )
    return sorted_bookings, title

def get_admin_bookings_list_keyboard(bookings_on_page: list, page: int, total_pages: int, period: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for booking in bookings_on_page:
        builder.row(
            types.InlineKeyboardButton(
                text=f"📄 Подробнее #{booking['id']}",
                callback_data=AdminBookingDetails(booking_id=booking['id'], page=page, period=period).pack()
            ),
            types.InlineKeyboardButton(
                text=f"❌ Отменить",
                callback_data=AdminCancelBooking(booking_id=booking['id'], page=page, period=period).pack()
            )
        )
    builder.adjust(1)
    pagination_row = []
    if page > 0:
        pagination_row.append(
            types.InlineKeyboardButton(text="⬅️", callback_data=AdminBookingsPaginator(action="prev", page=page, period=period).pack())
        )
    if page < total_pages - 1:
        pagination_row.append(
            types.InlineKeyboardButton(text="➡️", callback_data=AdminBookingsPaginator(action="next", page=page, period=period).pack())
        )
    if pagination_row:
        builder.row(*pagination_row)
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_booking_management"))
    return builder.as_markup()

async def _format_bookings_list(bookings: list, title: str) -> str:
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
            f"Услуга: {booking.get('service', 'Не указана')}\n"
            f"Клиент: {client_info}\n"
        )
        if comment := booking.get('comment'):
            response_text += f"<b>Комментарий:</b> <b>{comment}</b>\n"
        response_text += "---\n"
    return response_text

@router.callback_query(F.data == "admin_booking_management")
async def booking_management(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите период для просмотра записей или действие:",
        reply_markup=get_booking_management_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_bookings_"))
async def show_bookings_period(callback: CallbackQuery):
    period = callback.data.split("_")[-1]
    filtered_bookings, title = await _get_filtered_bookings(period)
    if not filtered_bookings:
        await callback.message.edit_text(
            await _format_bookings_list(filtered_bookings, title),
            reply_markup=get_back_to_menu_keyboard("admin_booking_management")
        )
        return
    page = 0
    total_pages = math.ceil(len(filtered_bookings) / ADMIN_ITEMS_PER_PAGE)
    bookings_on_page = filtered_bookings[0:ADMIN_ITEMS_PER_PAGE]
    response_text = await _format_bookings_list(bookings_on_page, title)
    await callback.message.edit_text(
        response_text,
        reply_markup=get_admin_bookings_list_keyboard(
            bookings_on_page=bookings_on_page, page=page, total_pages=total_pages, period=period
        )
    )
    await callback.answer()

@router.callback_query(AdminBookingDetails.filter())
async def show_booking_details(callback: types.CallbackQuery, callback_data: AdminBookingDetails, bot: Bot):
    """Показывает детальную информацию о записи по кнопке 'Подробнее'."""
    await callback.answer("Загружаю детали...")
    booking_id = callback_data.booking_id
    booking = await get_booking_by_id(booking_id)

    if not booking:
        await callback.answer(f"Запись с ID {booking_id} не найдена.", show_alert=True)
        return

    info_text = format_booking_details_for_admin(booking)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ Назад к списку",
        callback_data=AdminBookingsPaginator(action="noop", page=callback_data.page, period=callback_data.period).pack()
    )

    media_files = booking.get("media_files", [])

    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logger.warning(f"Could not delete message {callback.message.message_id} in chat {callback.message.chat.id}: {e}")

    if not media_files:
        await bot.send_message(callback.from_user.id, info_text, reply_markup=builder.as_markup())
    elif len(media_files) == 1:
        media = media_files[0]
        send_func = bot.send_photo if media['type'] == 'photo' else bot.send_video
        await send_func(callback.from_user.id, media['file_id'], caption=info_text, reply_markup=builder.as_markup())
    else:
        media_group = []
        for i, m in enumerate(media_files):
            caption = info_text if i == 0 else None
            media_input = InputMediaPhoto(media=m['file_id'], caption=caption) if m['type'] == 'photo' else InputMediaVideo(media=m['file_id'], caption=caption)
            media_group.append(media_input)
        await bot.send_media_group(callback.from_user.id, media=media_group)
        # Из-за ограничений API, клавиатуру для медиа-группы нужно отправлять отдельным сообщением
        await bot.send_message(callback.from_user.id, "Меню управления:", reply_markup=builder.as_markup())

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
        reply_markup=get_admin_bookings_list_keyboard(
            bookings_on_page=bookings_on_page, page=page, total_pages=total_pages, period=period
        )
    )
    await callback.answer()

@router.callback_query(AdminCancelBooking.filter())
async def cancel_booking_by_admin_inline(callback: CallbackQuery, callback_data: AdminCancelBooking, bot: Bot):
    booking_id = callback_data.booking_id
    cancelled_booking = await cancel_booking_in_db(booking_id=booking_id, user_id=None)
    if not cancelled_booking:
        await callback.answer("⚠️ Не удалось отменить запись. Возможно, она уже отменена.", show_alert=True)
        return
    await cancel_reminder(booking_id=booking_id)
    client_user_id = cancelled_booking.get('user_id')
    if client_user_id:
        try:
            await bot.send_message(client_user_id, "❗️ <b>Ваша запись была отменена администратором.</b>")
            logger.info(f"Sent cancellation notification to user {client_user_id} for booking {booking_id}")
        except Exception as e:
            logger.error(f"Failed to send cancellation notification to user {client_user_id}. Error: {e}")
    await callback.answer(f"✅ Запись #{booking_id} отменена.", show_alert=False)
    
    # Update message
    period = callback_data.period
    page = callback_data.page
    filtered_bookings, title = await _get_filtered_bookings(period)
    total_pages = math.ceil(len(filtered_bookings) / ADMIN_ITEMS_PER_PAGE)
    if page >= total_pages and page > 0:
        page -= 1
    start_index = page * ADMIN_ITEMS_PER_PAGE
    bookings_on_page = filtered_bookings[start_index : start_index + ADMIN_ITEMS_PER_PAGE]
    response_text = await _format_bookings_list(bookings_on_page, title)
    try:
        await callback.message.edit_text(
            response_text,
            reply_markup=get_admin_bookings_list_keyboard(
                bookings_on_page=bookings_on_page, page=page, total_pages=total_pages, period=period
            ) if bookings_on_page else get_back_to_menu_keyboard("admin_booking_management")
        )
    except TelegramBadRequest:
        logger.warning("Tried to edit message with the same content. Ignoring.")

@router.callback_query(F.data == "admin_manage_closed_days")
async def manage_closed_days_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.choosing_date_to_toggle_block)
    blocked_dates_raw = await get_blocked_dates()
    text = "🗓️ <b>Управление выходными днями</b>\n\nНажмите на дату, чтобы сделать ее выходным или рабочим.\n\n"
    if blocked_dates_raw:
        sorted_dates = sorted([datetime.strptime(d, "%d.%m.%Y") for d in blocked_dates_raw])
        text += "<b>Текущие выходные:</b>\n" + "\n".join([d.strftime("%d.%m.%Y") for d in sorted_dates])
    else:
        text += "Вручную установленных выходных нет."
    await callback.message.edit_text(text, reply_markup=create_admin_day_management_calendar())

@router.callback_query(StatsCalendarCallback.filter(F.action.in_(["prev-month", "next-month"])), AdminStates.choosing_date_to_toggle_block)
async def manage_closed_days_navigate(callback: CallbackQuery, callback_data: StatsCalendarCallback):
    year, month = callback_data.year, callback_data.month
    month += 1 if callback_data.action == "next-month" else -1
    if month == 0: month, year = 12, year - 1
    if month == 13: month, year = 1, year + 1
    await callback.message.edit_reply_markup(reply_markup=create_admin_day_management_calendar(year=year, month=month))

@router.callback_query(StatsCalendarCallback.filter(F.action == "select-day"), AdminStates.choosing_date_to_toggle_block)
async def toggle_closed_day(callback: CallbackQuery, callback_data: StatsCalendarCallback, state: FSMContext):
    selected_date = date(year=callback_data.year, month=callback_data.month, day=callback_data.day)
    date_str = selected_date.strftime("%d.%m.%Y")
    blocked_dates = await get_blocked_dates()
    if date_str in blocked_dates:
        await remove_blocked_date(date_str)
        await callback.answer(f"Дата {date_str} сделана рабочей.", show_alert=True)
    else:
        await add_blocked_date(date_str)
        await callback.answer(f"Дата {date_str} сделана выходным.", show_alert=True)
    await manage_closed_days_start(callback, state)