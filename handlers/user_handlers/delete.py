from aiogram.types import Message
from services.user_services import UserService
from .. import del_message
from aiogram import F
from logger import logger

async def del_user_directly(db, message: Message = None, username: str = None):
    """Delete a user directly from /user command with username"""
    try:

        # Delete the user
        del_user = UserService.del_user(db=db, username=username)

        if del_user is None:
            response = await message.answer("❌ مشکلی در حذف کاربر به وجود آمد. لطفاً دوباره تلاش کنید")
        elif del_user == "NOT_EXIST":
            response = await message.answer("❌ این کاربر وجود ندارد")
        else:
            response = await message.answer("✅ کاربر با موفقیت حذف شد.")

        # Delete final response and message after 3 seconds
        await del_message(3, response, message)
        return
    
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await message.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")

