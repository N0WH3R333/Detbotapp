import logging
from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router()


@router.error()
async def global_error_handler(event: ErrorEvent):
    """
    Global error handler. Catches all exceptions from handlers.
    """
    exception = event.exception

    # A common non-critical error when trying to edit a message with the same content.
    if isinstance(exception, TelegramBadRequest) and "message is not modified" in exception.message:
        logger.warning("Caught 'message is not modified' error. Ignoring.")
        # Acknowledge the callback query to stop the "loading" animation on the user's end.
        if event.update.callback_query:
            await event.update.callback_query.answer()
        return True

    # For all other errors, log them.
    logger.error(f"Unhandled exception for update {event.update.update_id}: {exception}", exc_info=True)

    # If the error came from a callback query, we should answer it to remove the "loading" state
    # and optionally notify the user.
    if event.update.callback_query:
        try:
            await event.update.callback_query.answer(
                "Произошла непредвиденная ошибка. Мы уже работаем над этим. Попробуйте позже.", show_alert=True
            )
        except Exception:
            pass  # Ignore if we can't even answer the callback

    # Returning True tells aiogram that the exception is handled.
    return True