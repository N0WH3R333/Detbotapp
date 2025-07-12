import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from config import ADMIN_IDS
from database.db import get_blocked_users

logger = logging.getLogger(__name__)

class BlockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Получаем объект пользователя из события
        user = data.get("event_from_user")
        if not user or (user.id in ADMIN_IDS):
            return await handler(event, data)

        # Проверяем, заблокирован ли пользователь
        if user.id in await get_blocked_users():
            logger.warning(f"Ignoring update from blocked user {user.id}")
            return  # Игнорируем обновление, не передавая его дальше

        return await handler(event, data)