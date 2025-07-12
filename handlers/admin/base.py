from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from keyboards.admin_inline import get_admin_keyboard

router = Router()

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Открывает админ-панель."""
    await state.clear()
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext):
    """Возвращает в главное меню админки, редактируя сообщение."""
    await state.clear()
    await callback.message.edit_text(
        "Добро пожаловать в админ-панель!",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()