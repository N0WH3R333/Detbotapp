import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import add_candidate_to_db
from config import ADMIN_IDS
from keyboards.reply import get_main_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)

HIRING_INFO_TEXT = """
<b>🛠️ Работа в нашем детейлинг-центре!</b>

Мы всегда в поиске талантливых и увлеченных своим делом людей. Если вы любите автомобили так же, как и мы, и хотите стать частью нашей команды, мы будем рады рассмотреть вашу кандидатуру.

<b>Что мы предлагаем:</b>
- Дружный коллектив профессионалов.
- Работа с современным оборудованием и качественными материалами.
- Возможности для роста и обучения.
- Достойная оплата труда.

<b>Кого мы ищем:</b>
- Мастеров по полировке и нанесению защитных покрытий.
- Специалистов по химчистке салона.
- Администраторов.

Если вас заинтересовала одна из вакансий или вы хотите предложить свою кандидатуру, пожалуйста, отправьте нам сообщение. Расскажите немного о себе, вашем опыте и почему вы хотите работать у нас. Вы также можете прикрепить резюме (документом).
"""

class HiringStates(StatesGroup):
    writing_application = State()

def get_apply_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Откликнуться", callback_data="apply_now")
    return builder.as_markup()

@router.message(F.text == "🛠️ Работа у нас")
async def show_hiring_info(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        HIRING_INFO_TEXT,
        reply_markup=get_apply_keyboard()
    )

@router.callback_query(F.data == "apply_now")
async def start_application(callback: CallbackQuery, state: FSMContext):
    await state.set_state(HiringStates.writing_application)
    await callback.message.edit_text(
        "Пожалуйста, отправьте ваше сообщение. Вы можете прикрепить один файл (резюме) к вашему тексту.",
        reply_markup=None
    )
    await callback.answer()

@router.message(HiringStates.writing_application, F.text | F.document)
async def process_application(message: Message, state: FSMContext, bot: Bot):
    user = message.from_user
    text = message.text or message.caption or ""
    file_id = message.document.file_id if message.document else None
    file_name = message.document.file_name if message.document else None

    if not text and not file_id:
        await message.answer("Пожалуйста, отправьте текстовое сообщение или прикрепите файл.")
        return

    new_candidate = await add_candidate_to_db(
        user_id=user.id, user_full_name=user.full_name, user_username=user.username,
        message_text=text, file_id=file_id, file_name=file_name
    )

    if ADMIN_IDS:
        admin_text = (
            f"📬 <b>Новый отклик на вакансию! (ID: {new_candidate['id']})</b>\n\n"
            f"<b>Кандидат:</b> {user.full_name} (<code>{user.id}</code>, @{user.username or 'не указан'})\n\n"
            f"<b>Сообщение:</b>\n<pre>{text or 'Нет текста.'}</pre>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await (bot.send_document(admin_id, document=file_id, caption=admin_text) if file_id else bot.send_message(admin_id, admin_text))
            except Exception as e:
                logger.error(f"Failed to send new candidate notification to admin {admin_id}: {e}")

    await message.answer(
        "✅ Спасибо! Ваш отклик получен. Мы свяжемся с вами, если ваша кандидатура нас заинтересует.",
        reply_markup=get_main_menu_keyboard()
    )
    await state.clear()