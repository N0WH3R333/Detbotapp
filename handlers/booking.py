from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import logging
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, User
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.calendar import create_calendar, CalendarCallback
from keyboards.inline import get_time_slots_keyboard
from keyboards.booking_keyboards import (
    get_services_keyboard, get_car_size_keyboard, get_polishing_type_keyboard,
    get_ceramics_type_keyboard, get_wrapping_type_keyboard,
    get_dry_cleaning_next_step_keyboard, get_interior_type_keyboard,
    get_dirt_level_keyboard, get_promocode_keyboard, get_comment_keyboard
)
from database.db import add_booking_to_db, get_all_prices, get_all_bookings, get_blocked_dates, get_all_promocodes, increment_promocode_usage
from utils.scheduler import schedule_reminder
from utils.constants import ALL_NAMES, WORKING_HOURS
from config import ADMIN_IDS, MAX_PARALLEL_BOOKINGS

MAX_MEDIA_FILES = 10

router = Router()
logger = logging.getLogger(__name__)


# =============================================================================
# FSM States for the booking process
# =============================================================================
class Booking(StatesGroup):
    choosing_service = State()
    choosing_car_size = State()
    choosing_service_type = State()  # For polishing and ceramics
    choosing_dry_cleaning_next_step = State() # For dry cleaning intermediate step
    choosing_interior_type = State()  # For dry cleaning
    choosing_dirt_level = State()  # For dry cleaning

    entering_comment = State()
    # Состояния для выбора даты и времени
    choosing_date = State()
    choosing_time = State()
    entering_promocode = State()

# =============================================================================
# Helper function and data for summary
# =============================================================================

async def calculate_booking_price(data: dict) -> tuple[int, int, float]:
    """
    Рассчитывает базовую стоимость, сумму скидки и итоговую стоимость.
    Возвращает кортеж (base_price, discount_amount, final_price).
    """
    prices = await get_all_prices()
    base_price = 0
    try:
        service = data.get('service')
        price_branch = prices.get(service)

        if isinstance(price_branch, int):  # Для простых услуг
            base_price = price_branch

        if isinstance(price_branch, dict):
            car_size = data.get('car_size')
            price_branch = price_branch.get(car_size)

            if service in ["polishing", "ceramics", "wrapping"]:
                base_price = price_branch.get(data.get('service_type'), 0)
            if service == "dry_cleaning":
                base_price = price_branch.get(data.get('interior_type'), {}).get(data.get('dirt_level'), 0)
    except (AttributeError, TypeError):
        base_price = 0  # Возвращаем 0, если что-то пошло не так

    discount_percent = data.get('discount_percent', 0)
    discount_amount = base_price * discount_percent / 100
    final_price = base_price - discount_amount
    return base_price, discount_amount, final_price

async def get_booking_summary(data: dict) -> str:
    """Формирует текстовое описание и стоимость выбранных услуг."""
    summary_parts = []
    if service := data.get('service'):
        summary_parts.append(f"<b>Основная услуга:</b> {ALL_NAMES.get(service, service)}")
    if car_size := data.get('car_size'):
        summary_parts.append(f"<b>Размер автомобиля:</b> {ALL_NAMES.get(car_size, car_size)}")
    if service_type := data.get('service_type'):
        summary_parts.append(f"<b>Тип:</b> {ALL_NAMES.get(service_type, service_type)}")
    if interior_type := data.get('interior_type'):
        summary_parts.append(f"<b>Тип салона:</b> {ALL_NAMES.get(interior_type, interior_type)}")
    if dirt_level := data.get('dirt_level'):
        summary_parts.append(f"<b>Степень загрязнения:</b> {ALL_NAMES.get(dirt_level, dirt_level)}")
    if comment := data.get('comment'):
        summary_parts.append(f"<b>Комментарий:</b> <b>{comment}</b>")
    if media_files := data.get('media_files'):
        if len(media_files) > 0:
            summary_parts.append(f"<b>✓ Медиафайлы: {len(media_files)} шт.</b>")

    base_price, discount_amount, final_price = await calculate_booking_price(data)

    if base_price > 0:
        summary_parts.append(f"\n<b>Стоимость:</b> {base_price} руб.")
        if discount_amount > 0:
            summary_parts.append(f"<b>Скидка ({data.get('discount_percent', 0)}%):</b> -{discount_amount:.2f} руб.")
            summary_parts.append(f"<b>Итого к оплате:</b> {final_price:.2f} руб.")
        
    return "\n".join(summary_parts)


# =============================================================================
# Handlers for the booking process
# =============================================================================

@router.message(F.text == "✨ Наши услуги")
async def start_booking(message: Message, state: FSMContext):
    """Начало процесса записи, вызывается по кнопке 'Наши услуги'."""
    await state.clear()
    await message.answer(
        "Выберите интересующую вас услугу:",
        reply_markup=get_services_keyboard()
    )
    await state.set_state(Booking.choosing_service)

@router.callback_query(F.data.startswith("service:"), Booking.choosing_service)
async def service_chosen(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора основной услуги."""
    service = callback.data.split(":")[1]
    await state.update_data(service=service)

    if service in ["polishing", "ceramics", "dry_cleaning", "wrapping"]:
        await callback.message.edit_text(
            "Отлично! Теперь выберите размер вашего автомобиля:",
            reply_markup=get_car_size_keyboard(service)
        )
        await state.set_state(Booking.choosing_car_size)
    elif service in ["washing", "glass_polishing"]:
        # Для простых услуг без доп. опций переходим сразу к вводу комментария
        await ask_for_comment(callback.message, state)
    else: # Обработка непредусмотренных или новых услуг
        await callback.answer("Заказ этой услуги находится в разработке.", show_alert=True)
    await callback.answer()

@router.callback_query(F.data.startswith("car_size:"), Booking.choosing_car_size)
async def car_size_chosen(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора размера кузова."""
    _, service, car_size = callback.data.split(":")
    await state.update_data(car_size=car_size)

    if service == "polishing":
        await callback.message.edit_text("Выберите тип полировки:", reply_markup=get_polishing_type_keyboard())
        await state.set_state(Booking.choosing_service_type)
    elif service == "ceramics":
        await callback.message.edit_text("Выберите тип керамического покрытия:", reply_markup=get_ceramics_type_keyboard())
        await state.set_state(Booking.choosing_service_type)
    elif service == "wrapping":
        await callback.message.edit_text("Выберите тип оклейки:", reply_markup=get_wrapping_type_keyboard())
        await state.set_state(Booking.choosing_service_type)
    elif service == "dry_cleaning":
        await callback.message.edit_text("Следующий шаг:", reply_markup=get_dry_cleaning_next_step_keyboard())
        await state.set_state(Booking.choosing_dry_cleaning_next_step)
    await callback.answer()

async def get_unavailable_dates_for_month(year: int, month: int) -> list[date]:
    """
    Возвращает список полностью занятых или заблокированных вручную дат для указанного месяца. (Оптимизированная версия)
    """
    # 1. Получаем все данные один раз
    manually_blocked_raw = await get_blocked_dates()
    all_bookings = await get_all_bookings()

    # 2. Фильтруем заблокированные вручную даты для текущего месяца
    unavailable_dates = set()
    for date_str in manually_blocked_raw:
        try:
            d = datetime.strptime(date_str, "%d.%m.%Y").date()
            if d.year == year and d.month == month:
                unavailable_dates.add(d)
        except ValueError:
            continue

    # 3. Группируем записи по датам только для нужного месяца
    bookings_in_month = defaultdict(list)
    for booking in all_bookings:
        date_str = booking.get('date')
        if not date_str:
            continue
        try:
            booking_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            if booking_date.year == year and booking_date.month == month:
                bookings_in_month[booking_date].append(booking.get('time'))
        except (ValueError, KeyError):
            continue

    # 4. Определяем полностью занятые дни на основе сгруппированных данных
    total_slots_per_day = len(WORKING_HOURS)
    for day, times in bookings_in_month.items():
        time_slot_counts = Counter(times)
        # Если количество слотов, достигших лимита, равно общему количеству рабочих слотов
        if sum(1 for slot in WORKING_HOURS if time_slot_counts.get(slot, 0) >= MAX_PARALLEL_BOOKINGS) >= total_slots_per_day:
            unavailable_dates.add(day)

    return sorted(list(unavailable_dates))


async def proceed_to_date_selection(message: Message, state: FSMContext, is_edit: bool = True):
    """Переходит к выбору даты, показывая календарь с учетом занятых дней."""
    now = datetime.now()
    unavailable_dates = await get_unavailable_dates_for_month(now.year, now.month)
    text = "Отлично! Теперь выберите удобную дату для записи:"
    markup = create_calendar(unavailable_dates=unavailable_dates)
    
    if is_edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)

    await state.set_state(Booking.choosing_date)

async def ask_for_comment(message: Message, state: FSMContext):
    """Спрашивает у пользователя комментарий/фото."""
    # Инициализируем/очищаем данные для этого шага
    await state.update_data(media_files=[], comment=None)
    await message.edit_text(
        f"Хотите оставить комментарий к записи или прикрепить фото/видео (до {MAX_MEDIA_FILES} шт.)?\n\n"
        "Отправьте медиафайлы и/или текстовый комментарий. Когда закончите, нажмите 'Далее'.",
        reply_markup=get_comment_keyboard()
    )
    await state.set_state(Booking.entering_comment)

async def ask_for_promocode(message: Message, state: FSMContext, is_edit: bool = True):
    """Спрашивает у пользователя промокод."""
    text = "У вас есть промокод на услуги? Если да, введите его. Если нет, нажмите 'Пропустить'."
    markup = get_promocode_keyboard()
    if is_edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)
    await state.set_state(Booking.entering_promocode)

@router.callback_query(F.data.startswith("service_type:"), Booking.choosing_service_type)
async def service_type_chosen(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа полировки/керамики."""
    service_type = callback.data.split(":")[1]
    await state.update_data(service_type=service_type)
    
    # Переход к вводу комментария
    await ask_for_comment(callback.message, state)
    await callback.answer()

# --- Handlers for Dry Cleaning flow ---

@router.callback_query(F.data == "dry_cleaning:select_interior", Booking.choosing_dry_cleaning_next_step)
async def select_interior_type(callback: CallbackQuery, state: FSMContext):
    """Переход к выбору типа салона для химчистки."""
    await callback.message.edit_text("Укажите тип салона:", reply_markup=get_interior_type_keyboard())
    await state.set_state(Booking.choosing_interior_type)
    await callback.answer()

@router.callback_query(F.data.startswith("interior_type:"), Booking.choosing_interior_type)
async def interior_type_chosen(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа салона."""
    interior_type = callback.data.split(":")[1]
    await state.update_data(interior_type=interior_type)
    await callback.message.edit_text("Укажите степень загрязнения:", reply_markup=get_dirt_level_keyboard())
    await state.set_state(Booking.choosing_dirt_level)
    await callback.answer()

@router.callback_query(F.data.startswith("dirt_level:"), Booking.choosing_dirt_level)
async def dirt_level_chosen(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора степени загрязнения."""
    dirt_level = callback.data.split(":")[1]
    await state.update_data(dirt_level=dirt_level)

    # Переход к вводу комментария
    await ask_for_comment(callback.message, state)
    await callback.answer()

# --- Handlers for Comment ---

@router.message(Booking.entering_comment, F.photo | F.video)
async def process_comment_media(message: Message, state: FSMContext):
    """Обрабатывает медиафайлы, присланные для комментария."""
    data = await state.get_data()
    media_files = data.get('media_files', [])

    if len(media_files) >= MAX_MEDIA_FILES:
        await message.answer(f"Вы достигли лимита в {MAX_MEDIA_FILES} медиафайлов. Нажмите 'Далее', чтобы продолжить.", reply_markup=get_comment_keyboard())
        return

    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    file_type = "photo" if message.photo else "video"
    media_files.append({"type": file_type, "file_id": file_id})

    # Если у медиа есть подпись, сохраняем ее как комментарий
    if message.caption:
        await state.update_data(comment=message.caption)

    await state.update_data(media_files=media_files)
    remaining = MAX_MEDIA_FILES - len(media_files)
    await message.answer(f"✅ Медиафайл получен. Можете отправить еще ({remaining} осталось) или нажмите 'Далее'.", reply_markup=get_comment_keyboard())


@router.message(Booking.entering_comment, F.text, ~F.text.startswith('/'))
async def process_comment_text(message: Message, state: FSMContext):
    """Обрабатывает текстовый комментарий, игнорируя команды."""
    await state.update_data(comment=message.text)
    await message.answer("✅ Комментарий сохранен. Можете прикрепить медиафайлы или нажмите 'Далее'.", reply_markup=get_comment_keyboard())


@router.callback_query(Booking.entering_comment, F.data == "comment:skip")
async def skip_comment(callback: CallbackQuery, state: FSMContext):
    """Пропускает ввод комментария или завершает его, если что-то было введено."""
    # Эта кнопка теперь работает как "Далее"
    await ask_for_promocode(callback.message, state, is_edit=True)
    await callback.answer()

# --- Handlers for Promocode ---

@router.message(Booking.entering_promocode, F.text, ~F.text.startswith('/'))
async def process_booking_promocode(message: Message, state: FSMContext):
    """Проверяет промокод и переходит к выбору даты, игнорируя команды."""
    promocode = message.text.upper()
    promo_data = (await get_all_promocodes()).get(promocode)

    # Guard clauses for invalid conditions
    if not promo_data or promo_data.get("type") != "detailing":
        await state.update_data(promocode=None, discount_percent=0)
        await message.answer("❌ Промокод недействителен или не подходит для услуг. Продолжаем без скидки.")
        await proceed_to_date_selection(message, state, is_edit=False)
        return

    try:
        today = datetime.now().date()
        start_date = datetime.strptime(promo_data.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.strptime(promo_data.get("end_date"), "%Y-%m-%d").date()

        if not (start_date <= today <= end_date):
            raise ValueError("Promocode is expired")

        usage_limit = promo_data.get("usage_limit")
        if usage_limit is not None and promo_data.get("times_used", 0) >= usage_limit:
            raise ValueError("Usage limit reached")
    except (ValueError, KeyError, TypeError):
        await state.update_data(promocode=None, discount_percent=0)
        await message.answer("❌ Промокод недействителен или не подходит для услуг. Продолжаем без скидки.")
        await proceed_to_date_selection(message, state, is_edit=False)
        return

    # Success case
    discount = promo_data.get("discount", 0)
    await state.update_data(promocode=promocode, discount_percent=discount)
    await message.answer(f"✅ Промокод '{promocode}' принят! Ваша скидка: {discount}%.")
    await proceed_to_date_selection(message, state, is_edit=False)

@router.callback_query(Booking.entering_promocode, F.data == "promo:skip")
async def skip_promocode(callback: CallbackQuery, state: FSMContext):
    """Пропускает ввод промокода и переходит к выбору даты."""
    await state.update_data(promocode=None, discount_percent=0)
    await proceed_to_date_selection(callback.message, state, is_edit=True)
    await callback.answer()


# --- Handlers for Date and Time selection ---

async def get_time_slots_occupancy(selected_date: date) -> dict[str, int]:
    """
    Возвращает словарь с количеством записей для каждого временного слота
    в указанную дату.
    """
    if selected_date < datetime.now().date():
        return {slot: MAX_PARALLEL_BOOKINGS for slot in WORKING_HOURS}

    logger.debug(f"get_time_slots_occupancy: Checking for date: {selected_date}")
    selected_date_str = selected_date.strftime("%d.%m.%Y")
    all_bookings = await get_all_bookings()
    bookings_on_date = [b for b in all_bookings if b.get('date') == selected_date_str]
    time_slot_counts = Counter(b.get('time') for b in bookings_on_date)
    logger.debug(f"get_time_slots_occupancy: Found occupancy: {time_slot_counts}")
    return time_slot_counts

@router.callback_query(CalendarCallback.filter(F.action.in_(["prev-month", "next-month"])), Booking.choosing_date)
async def calendar_navigate(callback: CallbackQuery, callback_data: CalendarCallback):
    """Обработка навигации по календарю."""
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
    
    unavailable_dates = await get_unavailable_dates_for_month(year, month)
    await callback.message.edit_reply_markup(
        reply_markup=create_calendar(year=year, month=month, unavailable_dates=unavailable_dates)
    )
    await callback.answer()


@router.callback_query(CalendarCallback.filter(F.action == "select-day"), Booking.choosing_date)
async def date_chosen(callback: CallbackQuery, callback_data: CalendarCallback, state: FSMContext):
    """Обработка выбора конкретного дня в календаре."""
    selected_date = date(year=callback_data.year, month=callback_data.month, day=callback_data.day)
    selected_date_str = selected_date.strftime("%d.%m.%Y")
    await state.update_data(date=selected_date_str)
    
    time_slot_occupancy = await get_time_slots_occupancy(selected_date)
    logger.debug(f"date_chosen: Building keyboard with occupancy: {time_slot_occupancy}")
    
    await callback.message.edit_text(
        f"Вы выбрали дату: {selected_date_str}\n\nТеперь выберите удобное время (❌ - занято):",
        reply_markup=get_time_slots_keyboard(
            occupancy=time_slot_occupancy,
            working_hours=WORKING_HOURS,
            max_bookings=MAX_PARALLEL_BOOKINGS
        )
    )
    await state.set_state(Booking.choosing_time)
    await callback.answer()

async def _save_booking_to_db(user: User, state_data: dict, final_price: float, discount_amount: float) -> dict:
    """Сохраняет данные о записи в базу данных и возвращает созданный объект."""
    booking_data_to_save = {
        "date": state_data.get("date"),
        "time": state_data.get("time"),
        "price": final_price,
        "promocode": state_data.get("promocode"),
        "discount_amount": discount_amount,
        "comment": state_data.get("comment"),
        "media_files": state_data.get("media_files", []),
        "service": ALL_NAMES.get(state_data.get("service"), "Неизвестная услуга"),
        "details": state_data
    }
    new_booking = await add_booking_to_db(
        user_id=user.id,
        user_full_name=user.full_name,
        user_username=user.username,
        booking_data=booking_data_to_save
    )
    return new_booking

async def _send_admin_notification(bot: Bot, user: User, new_booking: dict, summary_text: str):
    """Отправляет уведомление о новой записи администраторам."""
    if not ADMIN_IDS:
        return

    admin_text = (
        f"🔔 <b>Новая запись #{new_booking['id']}</b>\n\n"
        f"<b>Клиент:</b> {user.full_name}\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> @{user.username or 'не указан'}\n\n"
        f"<b>Дата и время:</b> {new_booking.get('date')} в {new_booking.get('time')}\n\n"
        f"<b>Выбранные услуги:</b>\n{summary_text}"
    )
    media_files = new_booking.get("media_files", [])

    for admin_id in ADMIN_IDS:
        try:
            if not media_files:
                await bot.send_message(admin_id, admin_text)
            elif len(media_files) == 1:
                media = media_files[0]
                if media['type'] == 'photo':
                    await bot.send_photo(admin_id, photo=media['file_id'], caption=admin_text)
                else:
                    await bot.send_video(admin_id, video=media['file_id'], caption=admin_text)
            else:
                media_group = [
                    InputMediaPhoto(media=m['file_id'], caption=admin_text if i == 0 else None) if m['type'] == 'photo'
                    else InputMediaVideo(media=m['file_id'], caption=admin_text if i == 0 else None)
                    for i, m in enumerate(media_files)
                ]
                await bot.send_media_group(admin_id, media=media_group)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору {admin_id}: {e}")

async def _send_admin_pending_notification(bot: Bot, user: User, new_booking: dict, summary_text: str):
    """Отправляет уведомление о новой заявке на запись администраторам с кнопкой подтверждения."""
    if not ADMIN_IDS:
        return

    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить запись",
        callback_data=f"adm_confirm_booking:{new_booking['id']}"
    )

    admin_text = (
        f"🔔 <b>Новая заявка на запись #{new_booking['id']}</b>\n\n"
        f"<b>Клиент:</b> {user.full_name}\n"
        f"<b>ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> @{user.username or 'не указан'}\n\n"
        f"<b>Дата и время:</b> {new_booking.get('date')} в {new_booking.get('time')}\n\n"
        f"<b>Выбранные услуги:</b>\n{summary_text}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=builder.as_markup())
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление о новой заявке администратору {admin_id}: {e}")

async def _finalize_booking_flow(callback: CallbackQuery, state: FSMContext, new_booking: dict, summary_text: str):
    """Завершает процесс бронирования: отправляет подтверждение, планирует напоминание, инкрементирует промокод."""
    user_confirmation_text = (
        "✅ <b>Запись успешна!</b>\n\n"
        "Мы ждем вас в назначенное время.\n\n"
        "<b>Детали вашей записи:</b>\n"
        f"{summary_text}\n\n"
        f"<b>Дата и время:</b> {new_booking.get('date')} в {new_booking.get('time')}\n\n"
        "📍 <b>Наш адрес:</b>\n"
        "Ставрополь, улица Старомарьевское шоссе 12 корпус 2\n\n"
        "📞 <b>Связаться с нами:</b>\n"
        "Администратор: <a href='tg://user?id=1973423865'>Написать в Telegram</a>\n\n"
        "🗺️ <b>Мы на карте:</b>\n"
        "<a href='https://2gis.ru/stavropol/geo/70030076147466365/42.012416,45.051523'>Открыть в 2ГИС</a>"
    )
    await callback.message.edit_text(user_confirmation_text, disable_web_page_preview=True)

    await schedule_reminder(new_booking)
    if new_booking.get("promocode"):
        await increment_promocode_usage(new_booking.get("promocode"))

    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("time:"), Booking.choosing_time)
async def time_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка выбора времени и завершение записи."""
    selected_time = ":".join(callback.data.split(":")[1:])
    user_data = await state.get_data()

    # Повторная проверка доступности слота на случай, если его заняли
    selected_date_obj = datetime.strptime(user_data.get("date"), "%d.%m.%Y").date()
    logger.debug(f"time_chosen: Re-checking slots for date: {selected_date_obj}")
    current_occupancy = await get_time_slots_occupancy(selected_date_obj)
    logger.debug(f"time_chosen: User selected '{selected_time}'. Occupancy now: {current_occupancy}")

    if current_occupancy.get(selected_time, 0) >= MAX_PARALLEL_BOOKINGS:
        await callback.answer("Это время уже занято!", show_alert=True)
        logger.warning(f"time_chosen: Slot conflict! User picked '{selected_time}', but it's already full.")
        await callback.message.edit_text(
            f"Извините, время <b>{selected_time}</b> только что заняли.\n\nПожалуйста, выберите другое доступное время (❌ - занято):",
            reply_markup=get_time_slots_keyboard(
                occupancy=current_occupancy,
                working_hours=WORKING_HOURS,
                max_bookings=MAX_PARALLEL_BOOKINGS
            )
        )
        return

    await state.update_data(time=selected_time)
    user_data = await state.get_data()

    # 1. Расчет цены
    base_price, discount_amount, final_price = await calculate_booking_price(user_data)

    # 2. Сохранение в БД
    new_booking = await _save_booking_to_db(callback.from_user, user_data, final_price, discount_amount)

    # 3. Формируем сводку для уведомлений
    summary_text = await get_booking_summary(user_data)

    # 4. Отправка уведомления админу с кнопкой подтверждения
    await _send_admin_pending_notification(bot, callback.from_user, new_booking, summary_text)

    # 5. Отправка предварительного подтверждения пользователю
    await callback.message.edit_text(
        "✅ <b>Ваша заявка принята!</b>\n\n"
        "Ожидайте, с вами свяжется администратор в ближайшее время для подтверждения записи."
    )

    # 6. Очистка состояния
    await state.clear()
    await callback.answer()
# =============================================================================
# Handlers for "Back" buttons
# =============================================================================

@router.callback_query(F.data == "back_to_calendar", Booking.choosing_time)
async def back_to_calendar(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору даты из выбора времени."""
    # Получаем текущий месяц и год для корректного отображения календаря
    now = datetime.now()
    unavailable_dates = await get_unavailable_dates_for_month(now.year, now.month)
    await callback.message.edit_text(
        "Выберите удобную дату для записи:",
        reply_markup=create_calendar(unavailable_dates=unavailable_dates)
    )
    await state.set_state(Booking.choosing_date)
    await callback.answer()

@router.callback_query(F.data == "back_to_services", Booking.choosing_date)
async def back_to_services_from_calendar(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору основной услуги из календаря (редактирует сообщение)."""
    await state.clear()
    await callback.message.edit_text(
        "Выберите интересующую вас услугу:",
        reply_markup=get_services_keyboard()
    )
    await state.set_state(Booking.choosing_service)
    await callback.answer()


@router.callback_query(F.data == "back:main_services", Booking.choosing_car_size)
async def back_to_main_services(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору основной услуги."""
    await callback.message.edit_text(
        "Выберите интересующую вас услугу:",
        reply_markup=get_services_keyboard()
    )
    await state.set_state(Booking.choosing_service)
    await callback.answer()

@router.callback_query(F.data.startswith("back:car_size:"), Booking.choosing_service_type)
async def back_to_car_size_from_types(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору размера кузова (из полировки/керамики)."""
    service = callback.data.split(":")[2]
    await callback.message.edit_text(
        "Отлично! Теперь выберите размер вашего автомобиля:",
        reply_markup=get_car_size_keyboard(service)
    )
    await state.set_state(Booking.choosing_car_size)
    await callback.answer()

@router.callback_query(F.data == "back:car_size:dry_cleaning", Booking.choosing_dry_cleaning_next_step)
async def back_to_car_size_from_dc_step(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору размера кузова (из химчистки)."""
    await callback.message.edit_text(
        "Отлично! Теперь выберите размер вашего автомобиля:",
        reply_markup=get_car_size_keyboard("dry_cleaning")
    )
    await state.set_state(Booking.choosing_car_size)
    await callback.answer()

@router.callback_query(F.data == "back:to_dc_next_step", Booking.choosing_interior_type)
async def back_to_dc_next_step(callback: CallbackQuery, state: FSMContext):
    """Возврат к шагу 'Тип салона'."""
    await callback.message.edit_text(
        "Следующий шаг:",
        reply_markup=get_dry_cleaning_next_step_keyboard()
    )
    await state.set_state(Booking.choosing_dry_cleaning_next_step)
    await callback.answer()

@router.callback_query(F.data == "back:interior_type", Booking.choosing_dirt_level)
async def back_to_interior_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа салона."""
    await callback.message.edit_text(
        "Укажите тип салона:",
        reply_markup=get_interior_type_keyboard()
    )
    await state.set_state(Booking.choosing_interior_type)
    await callback.answer()