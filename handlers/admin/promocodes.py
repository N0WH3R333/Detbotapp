import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .states import AdminStates
from database.db import get_all_promocodes, add_promocode_to_db
from keyboards.admin_inline import (
    get_promocode_management_keyboard, get_promocode_type_keyboard, get_back_to_menu_keyboard
)
from keyboards.calendar import create_stats_calendar, StatsCalendarCallback

logger = logging.getLogger(__name__)
router = Router()


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

            promo_type = f"({data.get('type', 'N/A')})"
            usage_text = ""
            limit = data.get("usage_limit")
            if limit is not None:
                used = data.get("times_used", 0)
                usage_text = f"({used}/{limit})"
            else:
                usage_text = f"({data.get('times_used', 0)}/∞)"

            text += f"{status_icon} <code>{code}</code> {promo_type} - {data.get('discount', '?')}% {date_range} {usage_text}\n"

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


@router.callback_query(F.data.startswith("admin_add_promo_type_"))
async def add_promo_type_selected(callback: CallbackQuery, state: FSMContext):
    """Начинает FSM для добавления промокода для магазина или детейлинга."""
    promo_type = callback.data.split("_")[-1]  # 'shop' or 'detailing'
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminStates.entering_promocode_code)
    await callback.message.edit_text("Введите промокод (например, `SALE25`):")
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
        promo_type = user_data.get("promo_type", "shop")  # По умолчанию - магазин

        await add_promocode_to_db(code, discount, start_date_str, end_date_str, usage_limit, promo_type)
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