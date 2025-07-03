import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError

from config import REMINDER_HOURS_BEFORE, ADMIN_ID, DAILY_REPORT_TIME, WEEKLY_REPORT_DAY_OF_WEEK, WEEKLY_REPORT_TIME
from database.db import get_all_bookings
from utils.bot_instance import bot_instance
from utils.reports import generate_period_report_text

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def send_report(period_days: int):
    """Отправляет отчет администратору."""
    if ADMIN_ID and bot_instance.bot:
        now = datetime.now()
        start_date = now - timedelta(days=period_days)
        report_text = await generate_period_report_text(start_date, now)
        await bot_instance.bot.send_message(ADMIN_ID, report_text)
        logger.info(f"Sent {period_days}-day report to admin {ADMIN_ID}")


async def send_booking_reminder(user_id: int, booking_id: int, service: str, date_str: str, time_str: str):
    """Отправляет напоминание о записи пользователю."""
    try:
        text = (
            f"👋 Напоминание о вашей записи!\n\n"
            f"Вы записаны на услугу <b>{service}</b>.\n"
            f"Ждем вас завтра, <b>{date_str}</b> в <b>{time_str}</b>.\n\n"
            f"До встречи!"
        )
        # Проверяем, что экземпляр бота доступен
        if bot_instance.bot:
            await bot_instance.bot.send_message(user_id, text)
        else:
            logger.error("Bot instance is not available in scheduler. Cannot send reminder.")
        logger.info(f"Sent reminder for booking #{booking_id} to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder for booking #{booking_id} to user {user_id}: {e}")


async def schedule_reminder(booking: dict):
    """Планирует отправку напоминания для одной записи."""
    try:
        booking_time_str = f"{booking['date']} {booking['time']}"
        booking_time = datetime.strptime(booking_time_str, "%d.%m.%Y %H:%M")

        reminder_time = booking_time - timedelta(hours=REMINDER_HOURS_BEFORE)

        if reminder_time > datetime.now():
            scheduler.add_job(
                send_booking_reminder,
                'date',
                run_date=reminder_time,
                args=[booking['user_id'], booking['id'], booking['service'], booking['date'], booking['time']],
                id=f"reminder_{booking['id']}",
                replace_existing=True
            )
            logger.info(f"Scheduled reminder for booking #{booking['id']} at {reminder_time}")
    except Exception as e:
        logger.error(f"Failed to schedule reminder for booking #{booking['id']}: {e}")


async def cancel_reminder(booking_id: int):
    """Отменяет запланированное напоминание для записи."""
    job_id = f"reminder_{booking_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Cancelled reminder for booking #{booking_id}")
    except JobLookupError:
        logger.warning(f"Could not find reminder job to cancel for booking #{booking_id}. It might have already been sent or was never scheduled.")
    except Exception as e:
        logger.error(f"Error cancelling reminder for booking #{booking_id}: {e}")


async def schedule_existing_reminders():
    """Планирует напоминания для всех существующих будущих записей при старте бота."""
    logger.info("Scheduling reminders for existing bookings...")
    all_bookings = await get_all_bookings()
    for booking in all_bookings:
        await schedule_reminder(booking)


def schedule_reports():
    """Планирует отправку ежедневных и еженедельных отчетов."""
    try:
        daily_hour, daily_minute = map(int, DAILY_REPORT_TIME.split(':'))
        weekly_hour, weekly_minute = map(int, WEEKLY_REPORT_TIME.split(':'))
        scheduler.add_job(send_report, 'cron', day_of_week='*', hour=daily_hour, minute=daily_minute, args=[1], id="daily_report")
        scheduler.add_job(send_report, 'cron', day_of_week=WEEKLY_REPORT_DAY_OF_WEEK, hour=weekly_hour, minute=weekly_minute, args=[7], id="weekly_report")
        logger.info(f"Scheduled daily reports for {DAILY_REPORT_TIME} and weekly for {WEEKLY_REPORT_DAY_OF_WEEK} at {WEEKLY_REPORT_TIME}.")
    except Exception as e:
        logger.error(f"Failed to schedule reports: {e}")