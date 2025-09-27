from aiogram import Router
from .funcs import get_main_menu_keyboard, chat_type_filter, del_message, get_callback
from .handler_requirements import admin_require

main_router = Router()

from . import start_handlers
from .task_handlers import add, edit
from .user_handlers import add, delete