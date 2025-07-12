import logging
from aiogram import Router, F, Bot, types
from aiogram.types import ChatMemberUpdated, CallbackQuery, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

router = Router()
# Ограничиваем роутер только групповыми чатами
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

WELCOME_MESSAGE = """
Добро пожаловать в чат, {user_mention}!

Чтобы получить доступ к общению и подтвердить, что вы не бот, пожалуйста, нажмите на кнопку ниже.
"""

# Хендлер на вход нового пользователя в чат
@router.chat_member(
    (F.old_chat_member.status.in_({ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED}))
    & (F.new_chat_member.status == ChatMemberStatus.MEMBER)
)
async def on_user_joined(event: ChatMemberUpdated, bot: Bot):
    """
    Обрабатывает вход нового пользователя.
    "Заглушает" его и отправляет сообщение с кнопкой для верификации.
    """
    user = event.new_chat_member.user
    chat_id = event.chat.id
    logger = logging.getLogger(__name__)

    # Пытаемся ограничить пользователя (замутить)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
        logger.info(f"Пользователь {user.id} ({user.full_name}) был ограничен в чате {chat_id}.")
    except TelegramBadRequest as e:
        # Если у бота нет прав, он не сможет замутить.
        logger.error(f"Не удалось ограничить пользователя {user.id} в чате {chat_id}: {e}")
        # Можно отправить сообщение администраторам о проблеме
        return

    # Создаем кнопку для верификации
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="Я не бот",
        callback_data=f"verify_user_{user.id}"
    ))

    # Отправляем приветственное сообщение с кнопкой
    await event.answer(
        text=WELCOME_MESSAGE.format(user_mention=user.mention_html()),
        reply_markup=builder.as_markup()
    )

# Хендлер для кнопки верификации
@router.callback_query(F.data.startswith("verify_user_"))
async def verify_user_callback(query: CallbackQuery, bot: Bot):
    """
    Обрабатывает нажатие на кнопку верификации.
    Снимает ограничения с пользователя.
    """
    logger = logging.getLogger(__name__)
    # Получаем ID пользователя из callback_data
    user_id_to_verify = int(query.data.split("_")[-1])

    # Проверяем, что кнопку нажал именно тот пользователь, для которого она предназначена
    if query.from_user.id != user_id_to_verify:
        await query.answer("Это кнопка не для вас.", show_alert=True)
        return

    # Снимаем ограничения, возвращая стандартные права группы
    try:
        await bot.restrict_chat_member(
            chat_id=query.message.chat.id,
            user_id=query.from_user.id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        logger.info(f"С пользователя {query.from_user.id} сняты ограничения в чате {query.message.chat.id}.")
        # Удаляем сообщение с кнопкой после успешной верификации
        await query.message.delete()
        await query.answer("Верификация пройдена! Добро пожаловать.", show_alert=False)
    except TelegramBadRequest as e:
        logger.error(f"Не удалось снять ограничения с {query.from_user.id} в чате {query.message.chat.id}: {e}")
        await query.answer("Произошла ошибка. Обратитесь к администратору.", show_alert=True)