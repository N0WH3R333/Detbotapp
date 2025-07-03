from datetime import datetime, date, timedelta
import calendar
import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from collections import Counter

from keyboards.inline import get_services_keyboard, get_time_slots_keyboard, get_payment_keyboard
from keyboards.calendar import create_calendar, CalendarCallback
from database.db import add_booking_to_db, get_all_bookings
from keyboards.reply import get_main_menu_keyboard
from config import WEBAPP_URL, MAX_PARALLEL_BOOKINGS
from utils.scheduler import schedule_reminder

logger = logging.getLogger(__name__)
router = Router()

ALL_TIME_SLOTS = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"]

SERVICES_DB = {
    "service_complex": {"name": "Комплексная мойка", "price": 2500, "duration_hours": 2},
    "service_polish": {"name": "Полировка кузова", "price": 10000, "duration_hours": 6},
    "service_dryclean": {"name": "Химчистка салона", "price": 5000, "duration_hours": 4},
}


def _get_daily_load(bookings_on_date: list[dict]) -> Counter:
    """Рассчитывает количество занятых постов для каждого часа в указанный день."""
    daily_load = Counter()
    for booking in bookings_on_date:
        try:
            start_hour = int(booking['time'].split(':')[0])
            duration = booking.get('duration_hours', 1)
            for i in range(duration):
                hour = start_hour + i
                time_slot = f"{hour:02d}:00"
                if time_slot in ALL_TIME_SLOTS:
                    daily_load[time_slot] += 1
        except (ValueError, KeyError, IndexError):
            continue
    return daily_load


def _calculate_unavailable_dates(bookings: list[dict], year: int, month: int) -> list[date]:
    """
    Вычисляет полностью забронированные даты, основываясь на суммарной загрузке по часам.
    День считается недоступным, если в нем не осталось слотов для самой короткой услуги.
    """
    shortest_service_duration = min(s.get('duration_hours', 1) for s in SERVICES_DB.values())

    # Группируем записи по датам для эффективности
    bookings_by_date = {}
    for b in bookings:
        try:
            booking_date_obj = datetime.strptime(b['date'], '%d.%m.%Y')
            if booking_date_obj.year == year and booking_date_obj.month == month:
                if b['date'] not in bookings_by_date:
                    bookings_by_date[b['date']] = []
                bookings_by_date[b['date']].append(b)
        except (ValueError, KeyError):
            continue

    fully_booked_dates = []

    # Проверяем каждый день в календаре
    num_days_in_month = calendar.monthrange(year, month)[1]
    for day in range(1, num_days_in_month + 1):
        current_date_str = f"{day:02d}.{month:02d}.{year}"
        bookings_on_this_day = bookings_by_date.get(current_date_str, [])
        daily_load = _get_daily_load(bookings_on_this_day)

        # Проверяем, можно ли вставить самую короткую услугу
        can_fit_shortest_service = False
        for i in range(len(ALL_TIME_SLOTS) - shortest_service_duration + 1):
            is_slot_available = all(daily_load[ALL_TIME_SLOTS[i + j]] < MAX_PARALLEL_BOOKINGS for j in range(shortest_service_duration))
            if is_slot_available:
                can_fit_shortest_service = True
                break  # Нашли свободный слот, день доступен

        if not can_fit_shortest_service:
            fully_booked_dates.append(date(year, month, day))

    return fully_booked_dates

# Определяем состояния (FSM) для процесса записи
class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    payment_confirmation = State()


# Хендлер на кнопку "🗓️ Записаться на услугу"
@router.message(F.text == "🗓️ Записаться на услугу")
async def start_booking(message: Message, state: FSMContext):
    logger.debug(f"User {message.from_user.id} started booking process.")
    # Убираем основную клавиатуру и показываем инлайн-клавиатуру с услугами
    await message.answer("Выберите услугу:", reply_markup=ReplyKeyboardRemove())
    await message.answer("Пожалуйста, выберите одну из наших услуг:", reply_markup=get_services_keyboard(SERVICES_DB))
    # Устанавливаем состояние ожидания выбора услуги
    await state.set_state(BookingStates.choosing_service)


# Хендлер для кнопки "Назад в главное меню" из списка услуг
@router.callback_query(BookingStates.choosing_service, F.data == "back_to_main_menu")
async def back_to_main_from_services(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Вы вернулись в главное меню.")
    # Отправляем новое сообщение, чтобы показать основную клавиатуру
    await callback.message.answer(
        "Выберите, что вас интересует:",
        reply_markup=get_main_menu_keyboard(webapp_url=WEBAPP_URL)
    )
    await callback.answer()


# Хендлер на выбор услуги (ловит callback)
@router.callback_query(BookingStates.choosing_service, F.data.startswith("service_"))
async def service_chosen(callback: CallbackQuery, state: FSMContext):
    logger.debug(f"User {callback.from_user.id} chose service. Callback: {callback.data}")
    service_id = callback.data
    service_info = SERVICES_DB.get(service_id)

    if not service_info:
        await callback.answer("Услуга не найдена, попробуйте снова.", show_alert=True)
        return

    # Сохраняем выбранную услугу и ее название в FSM
    await state.update_data(
        chosen_service_id=service_id,
        **service_info
    )

    # Редактируем сообщение, убирая кнопки и сообщая о выборе
    all_bookings = await get_all_bookings()
    now = datetime.now()
    unavailable_dates = _calculate_unavailable_dates(all_bookings, now.year, now.month)
    await callback.message.edit_text(
        f"Отлично! Вы выбрали: {service_info['name']}.\n\n"
        f"Теперь, пожалуйста, выберите дату.",
        reply_markup=create_calendar(unavailable_dates=unavailable_dates)
    )

    # Переводим пользователя в состояние выбора даты
    await state.set_state(BookingStates.choosing_date)
    # Отвечаем на callback, чтобы убрать "часики" на кнопке
    await callback.answer()


# Хендлер для навигации по календарю (вперед/назад)
@router.callback_query(BookingStates.choosing_date, CalendarCallback.filter(F.action.in_(["prev-month", "next-month"])))
async def calendar_navigate(callback: CallbackQuery, callback_data: CalendarCallback):
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

    all_bookings = await get_all_bookings()
    unavailable_dates = _calculate_unavailable_dates(all_bookings, year, month)
    await callback.message.edit_reply_markup(reply_markup=create_calendar(year=year, month=month, unavailable_dates=unavailable_dates))
    await callback.answer()


# Хендлер для кнопки "Назад к выбору услуг"
@router.callback_query(BookingStates.choosing_date, F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Пожалуйста, выберите одну из наших услуг:",
        reply_markup=get_services_keyboard(SERVICES_DB)
    )
    await state.set_state(BookingStates.choosing_service)
    await callback.answer()


# Хендлер для выбора дня в календаре
@router.callback_query(BookingStates.choosing_date, CalendarCallback.filter(F.action == "select-day"))
async def date_chosen(callback: CallbackQuery, callback_data: CalendarCallback, state: FSMContext):
    chosen_date_str = datetime(year=callback_data.year, month=callback_data.month, day=callback_data.day).strftime("%d.%m.%Y")
    user_data = await state.get_data()
    service_duration = user_data.get('duration_hours', 1)
    all_bookings = await get_all_bookings()

    # Собираем все записи на выбранный день и считаем загрузку по часам
    bookings_on_date = [b for b in all_bookings if b['date'] == chosen_date_str]
    daily_load = _get_daily_load(bookings_on_date)

    # Проверяем доступность каждого слота с учетом длительности услуги и количества мест
    available_slots = []
    for i in range(len(ALL_TIME_SLOTS) - service_duration + 1):
        slot_is_free = True
        # Проверяем все часы, которые займет услуга
        for j in range(service_duration):
            slot_to_check = ALL_TIME_SLOTS[i + j]
            if daily_load[slot_to_check] >= MAX_PARALLEL_BOOKINGS:
                slot_is_free = False
                break
        if slot_is_free:
            available_slots.append(ALL_TIME_SLOTS[i])

    await state.update_data(chosen_date=chosen_date_str)

    await callback.message.edit_text(
        f"Вы выбрали дату: {chosen_date_str}.\n\nТеперь выберите доступное время.",
        reply_markup=get_time_slots_keyboard(available_slots=available_slots)
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()


# Хендлер для кнопки "Назад к выбору даты"
@router.callback_query(BookingStates.choosing_time, F.data == "back_to_calendar")
async def back_to_calendar(callback: CallbackQuery, state: FSMContext):
    all_bookings = await get_all_bookings()
    now = datetime.now()
    unavailable_dates = _calculate_unavailable_dates(all_bookings, now.year, now.month)
    await callback.message.edit_text(
        "Пожалуйста, выберите дату.",
        reply_markup=create_calendar(unavailable_dates=unavailable_dates)
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()


# Хендлер для выбора времени
@router.callback_query(BookingStates.choosing_time, F.data.startswith("time_"))
async def time_chosen(callback: CallbackQuery, state: FSMContext):
    chosen_time = callback.data.split("_")[1]
    await state.update_data(chosen_time=chosen_time)

    # Получаем все данные из FSM
    user_data = await state.get_data()
    service_name = user_data.get("name", "Не указана")
    service_price = user_data.get("price", 0)
    chosen_date = user_data.get("chosen_date", "Не указана")

    # Формируем сообщение с итоговой информацией и просьбой подтвердить
    await callback.message.edit_text(
        f"<b>Пожалуйста, проверьте и подтвердите вашу запись:</b>\n\n"
        f"<b>Услуга:</b> {service_name}\n"
        f"<b>Стоимость:</b> {service_price} руб.\n"
        f"<b>Дата:</b> {chosen_date}\n"
        f"<b>Время:</b> {chosen_time}\n\n"
        f"Для подтверждения записи требуется предоплата.",
        reply_markup=get_payment_keyboard()
    )

    # Переводим в состояние ожидания подтверждения
    await state.set_state(BookingStates.payment_confirmation)
    await callback.answer()


# Хендлер для подтверждения и "оплаты"
@router.callback_query(BookingStates.payment_confirmation, F.data == "confirm_payment")
async def confirm_payment(callback: CallbackQuery, state: FSMContext):
    # 1. Получаем все данные из FSM
    user_data = await state.get_data()
    user = callback.from_user

    # 2. Формируем словарь с новой записью
    new_booking = {
        "service": user_data.get("name", "Не указана"),
        "price": user_data.get("price", 0),
        "duration_hours": user_data.get("duration_hours", 1),
        "date": user_data.get("chosen_date", "Не указана"),
        "time": user_data.get("chosen_time", "Не указана"),
    }

    # 3. Сохраняем новую запись в нашу "базу данных"
    new_booking_obj = await add_booking_to_db(
        user_id=user.id,
        user_full_name=user.full_name,
        user_username=user.username,
        booking_data=new_booking
    )

    # 3.5. Планируем напоминание
    await schedule_reminder(new_booking_obj)

    # 4. Отправляем подтверждение пользователю и завершаем FSM
    await callback.message.edit_text("✅ <b>Отлично! Ваша запись подтверждена и сохранена.</b>\n\nМы будем ждать вас!")
    await callback.message.answer("Вы в главном меню.", reply_markup=get_main_menu_keyboard(webapp_url=WEBAPP_URL))
    await state.clear()
    await callback.answer()


# Хендлер для отмены записи на этапе подтверждения
@router.callback_query(BookingStates.payment_confirmation, F.data == "cancel_booking")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Запись отменена.")
    await callback.message.answer("Вы в главном меню.", reply_markup=get_main_menu_keyboard(webapp_url=WEBAPP_URL))
    # Завершаем FSM и очищаем данные
    await state.clear()
    await callback.answer()