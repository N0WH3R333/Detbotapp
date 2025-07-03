import calendar
from datetime import datetime, date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CalendarCallback(CallbackData, prefix="calendar"):
    """
    Фабрика CallbackData для навигации и выбора даты в календаре.
    - action: "prev-month", "next-month", "select-day"
    - year, month, day: соответствующие значения даты
    """
    action: str
    year: int
    month: int
    day: int = 0  # Необязателен для навигации по месяцам


class StatsCalendarCallback(CallbackData, prefix="stats_calendar"):
    action: str
    year: int
    month: int
    day: int = 0


def create_calendar(year: int = None, month: int = None, unavailable_dates: list[date] = None) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с календарем для указанного месяца и года.
    """
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    if unavailable_dates is None:
        unavailable_dates = []

    builder = InlineKeyboardBuilder()

    # Кнопки навигации: < Месяц Год >
    builder.row(
        InlineKeyboardButton(text="<", callback_data=CalendarCallback(action="prev-month", year=year, month=month).pack()),
        InlineKeyboardButton(text=f"{calendar.month_name[month]} {year}", callback_data="ignore"),
        InlineKeyboardButton(text=">", callback_data=CalendarCallback(action="next-month", year=year, month=month).pack())
    )

    # Дни недели
    builder.row(*[InlineKeyboardButton(text=day, callback_data="ignore") for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]])

    # Дни месяца
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_buttons = []
        for day in week:
            current_date = datetime(year, month, day).date() if day != 0 else None
            if day == 0:
                row_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            elif current_date and (current_date < now.date() or current_date in unavailable_dates):
                row_buttons.append(InlineKeyboardButton(text=str(day), callback_data="ignore"))  # Прошедшие или занятые дни неактивны
            else:
                row_buttons.append(InlineKeyboardButton(text=str(day), callback_data=CalendarCallback(action="select-day", year=year, month=month, day=day).pack()))
        builder.row(*row_buttons)
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад к выбору услуг", callback_data="back_to_services"))

    return builder.as_markup()


def create_stats_calendar(year: int = None, month: int = None) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с календарем для выбора даты в статистике.
    Позволяет выбирать любые даты.
    """
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    builder = InlineKeyboardBuilder()

    # Кнопки навигации: < Месяц Год >
    builder.row(
        InlineKeyboardButton(text="<", callback_data=StatsCalendarCallback(action="prev-month", year=year, month=month).pack()),
        InlineKeyboardButton(text=f"{calendar.month_name[month]} {year}", callback_data="ignore"),
        InlineKeyboardButton(text=">", callback_data=StatsCalendarCallback(action="next-month", year=year, month=month).pack())
    )

    # Дни недели
    builder.row(*[InlineKeyboardButton(text=day, callback_data="ignore") for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]])

    # Дни месяца
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row_buttons = []
        for day in week:
            if day == 0:
                row_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row_buttons.append(InlineKeyboardButton(text=str(day), callback_data=StatsCalendarCallback(action="select-day", year=year, month=month, day=day).pack()))
        builder.row(*row_buttons)

    return builder.as_markup()
