from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import WebAppInfo


def get_main_menu_keyboard(webapp_url: str) -> ReplyKeyboardMarkup:
    """
    Создает и возвращает клавиатуру главного меню.
    """
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="✨ Наши услуги"),
        KeyboardButton(text="🛍️ Магазин", web_app=WebAppInfo(url=webapp_url))
    )
    builder.row(
        KeyboardButton(text="📓 Мои записи"),
        KeyboardButton(text="🛍️ Мои заказы")
    )
    builder.row(
        KeyboardButton(text="🛠️ Работа у нас"),
        KeyboardButton(text="📞 Контакты / Помощь")
    )

    return builder.as_markup(resize_keyboard=True)