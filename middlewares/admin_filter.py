from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from config import SUPER_ADMIN_ID

class IsSuperAdmin(Filter):
    """
    Проверяет, является ли пользователь, вызвавший событие,
    супер-администратором.
    """
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        # Проверяем, что SUPER_ADMIN_ID вообще задан
        if SUPER_ADMIN_ID is None:
            return False
        # Сравниваем ID пользователя с ID супер-админа
        return event.from_user.id == SUPER_ADMIN_ID