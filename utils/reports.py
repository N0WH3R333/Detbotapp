from collections import Counter
from datetime import datetime

from database.db import get_all_bookings, get_all_orders


def _get_top_clients_text(records: list, top_n: int = 3) -> str:
    """Формирует текст с топ-N клиентами по количеству записей/заказов."""
    if not records:
        return ""

    user_counts = Counter(r['user_id'] for r in records if 'user_id' in r)
    if not user_counts:
        return ""

    # Собираем информацию о пользователях, чтобы избежать дублирования
    user_info = {}
    for record in records:
        if 'user_id' in record and record['user_id'] not in user_info:
            user_info[record['user_id']] = {
                'name': record.get('user_full_name'),
                'username': record.get('user_username')
            }

    text = f"\n\n🏆 <b>Топ-{top_n} активных клиентов:</b>\n"
    for user_id, count in user_counts.most_common(top_n):
        info = user_info.get(user_id, {})
        name = info.get('name')
        username = info.get('username')

        if name:
            user_str = f"{name}"
            if username:
                user_str += f" (@{username})"
        else:
            user_str = f"ID: <code>{user_id}</code>"

        text += f"  • {user_str}: {count} раз(а)\n"

    return text


async def generate_period_report_text(start_date: datetime, end_date: datetime) -> str:
    """Генерирует текстовый отчет за указанный период."""
    all_bookings = await get_all_bookings()
    all_orders = await get_all_orders()

    # Фильтруем данные за период
    period_bookings = [
        b for b in all_bookings
        if 'date' in b and start_date <= datetime.strptime(b['date'], "%d.%m.%Y").replace(hour=0, minute=0, second=0) < end_date
    ]
    period_orders = [
        o for o in all_orders
        if 'date' in o and start_date <= datetime.strptime(o['date'], "%Y-%m-%d %H:%M:%S") < end_date
    ]

    # Расчет новых метрик
    total_revenue_orders = sum(o.get('total_price', 0) for o in period_orders)
    avg_check_orders = total_revenue_orders / len(period_orders) if period_orders else 0

    # Коэффициент повторных клиентов
    all_records = period_bookings + period_orders
    repeat_customer_rate = 0
    if all_records:
        user_counts = Counter(r['user_id'] for r in all_records)
        total_customers = len(user_counts)
        repeat_customers = sum(1 for count in user_counts.values() if count > 1)
        if total_customers > 0:
            repeat_customer_rate = (repeat_customers / total_customers) * 100

    # Определяем заголовок отчета
    period_days = (end_date - start_date).days
    if period_days <= 1:
        title = "Отчет за прошедший день"
    elif 6 <= period_days <= 8:
        title = "Отчет за прошедшую неделю"
    else:
        title = "Отчет за период"

    report_text = (
        f"📊 <b>{title}</b>\n"
        f"({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})\n\n"
        f"<b>Ключевые показатели:</b>\n"
        f"  - 📝 Новых записей: <b>{len(period_bookings)}</b>\n"
        f"  - 🛒 Новых заказов: <b>{len(period_orders)}</b>\n"
        f"  - 💰 Выручка с заказов: <b>{total_revenue_orders:.2f} руб.</b>\n"
        f"  - 📈 Средний чек (заказы): <b>{avg_check_orders:.2f} руб.</b>\n"
        f"  - 🔄 Коэф. повторных клиентов: <b>{repeat_customer_rate:.1f}%</b>\n"
    )

    # Объединяем записи и заказы для общего топа клиентов
    report_text += _get_top_clients_text(all_records)

    return report_text