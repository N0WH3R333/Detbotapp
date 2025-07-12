import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.admin_inline import get_admin_management_keyboard
from middlewares.admin_filter import IsSuperAdmin

logger = logging.getLogger(__name__)
router = Router()

# Применяем фильтр ко всему роутеру, чтобы защитить все его обработчики
router.callback_query.filter(IsSuperAdmin())


@router.callback_query(F.data == "admin_manage_admins")
async def manage_admins_menu(callback: CallbackQuery):
    """Показывает меню управления администраторами."""
    await callback.message.edit_text(
        "👑 <b>Раздел управления администрацией</b>\n\n"
        "Здесь вы можете добавлять и удалять администраторов.",
        reply_markup=get_admin_management_keyboard()
    )
    await callback.answer()