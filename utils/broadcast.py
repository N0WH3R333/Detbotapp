import asyncio
import logging
from typing import Dict, Any

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

from database.db import get_all_unique_user_ids
from keyboards.admin_inline import get_button_markup

logger = logging.getLogger(__name__)


async def send_broadcast(bot: Bot, user_ids: list[int], content: Dict[str, Any]) -> tuple[int, int]:
    """
    Выполняет рассылку сообщения указанным пользователям.

    :param bot: Экземпляр aiogram.Bot.
    :param user_ids: Список ID пользователей для рассылки.
    :param content: Словарь, описывающий сообщение (message_id, from_chat_id, button).
    :return: Кортеж (успешно отправлено, не удалось отправить).
    """
    if not user_ids:
        logger.info("Рассылка: нет пользователей для отправки.")
        return 0, 0
        
    logger.info(f"Начинается рассылка для {len(user_ids)} пользователей.")

    successful_sends = 0
    failed_sends = 0
    reply_markup = get_button_markup(content.get("button"))

    for user_id in user_ids:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=content['from_chat_id'],
                message_id=content['message_id'],
                reply_markup=reply_markup
            )
            successful_sends += 1
            logger.debug(f"Рассылка: сообщение успешно отправлено пользователю {user_id}")
            await asyncio.sleep(0.05)  # Защита от превышения лимитов Telegram (20-30 msg/sec)
        except TelegramRetryAfter as e:
            logger.warning(f"Рассылка: превышен лимит. Пауза на {e.retry_after} секунд.")
            await asyncio.sleep(e.retry_after)
            # Повторяем попытку для того же пользователя (простая реализация)
            continue
        except TelegramForbiddenError:
            logger.warning(f"Рассылка: пользователь {user_id} заблокировал бота.")
            failed_sends += 1
        except (TelegramAPIError, Exception) as e:
            logger.error(f"Рассылка: ошибка при отправке пользователю {user_id}: {e}")
            failed_sends += 1

    logger.info(f"Рассылка завершена. Успешно: {successful_sends}, Ошибки: {failed_sends}")
    return successful_sends, failed_sends