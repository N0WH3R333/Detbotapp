import logging
import io
import csv
import json
from datetime import datetime
from collections import Counter

from aiogram import F, Router, Bot, types
from aiogram.types import CallbackQuery

from .states import AdminStates
from database.db import get_all_bookings, get_all_orders
from keyboards.admin_inline import get_stats_menu_keyboard, get_back_to_menu_keyboard
from keyboards.calendar import create_stats_calendar, StatsCalendarCallback
from utils.reports import generate_period_report_text
from aiogram.fsm.context import FSMContext

# Для построения графиков. Не забудьте установить: pip install matplotlib
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

logger = logging.getLogger(__name__)
router = Router()


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
        if month == 0: month, year = 12, year - 1
    else:
        month += 1
        if month == 13: month, year = 1, year + 1

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

    if not start_date or start_date > end_date:
        await callback.answer("Ошибка: конечная дата не может быть раньше начальной!", show_alert=True)
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

    chart_buffer = _generate_bar_chart(service_counts, "Популярность услуг", "Услуга", "Количество записей")

    if chart_buffer:
        await bot.send_photo(callback.from_user.id, types.BufferedInputFile(chart_buffer.read(), "bookings_stats.png"), caption="Статистика по популярности услуг.")
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

    chart_buffer = _generate_bar_chart(promocode_counts, "Использование промокодов", "Промокод", "Количество использований")

    if chart_buffer:
        await bot.send_photo(callback.from_user.id, types.BufferedInputFile(chart_buffer.read(), "promocodes_stats.png"), caption="Статистика по использованию промокодов.")
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

    await bot.send_document(callback.from_user.id, types.BufferedInputFile(output.getvalue().encode('utf-8-sig'), "all_bookings.csv"), caption="Экспорт всех записей.")


@router.callback_query(F.data == "admin_export_orders_csv")
async def export_orders_csv(callback: CallbackQuery, bot: Bot):
    """Экспортирует все заказы в CSV файл."""
    await callback.answer("⏳ Готовлю файл...")
    all_orders = await get_all_orders()
    if not all_orders:
        await callback.message.answer("Нет заказов для экспорта.")
        return

    export_data = [order.copy() for order in all_orders]
    for order in export_data:
        order['cart'] = json.dumps(order.get('cart', {}), ensure_ascii=False)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=export_data[0].keys())
    writer.writeheader()
    writer.writerows(export_data)
    output.seek(0)

    await bot.send_document(callback.from_user.id, types.BufferedInputFile(output.getvalue().encode('utf-8-sig'), "all_orders.csv"), caption="Экспорт всех заказов.")