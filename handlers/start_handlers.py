from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ChatType
from services.task_services import TaskService
from services.user_services import UserService
from database import get_db
from logger import logger
from . import main_router as router
from . import chat_type_filter, get_main_menu_keyboard
from config import config

# ===== Start in Private chat =====
@router.message(Command("start"), chat_type_filter(ChatType.PRIVATE))
async def cmd_start_private(message: Message):
    """Handle /start command in private chats"""
    try:
        db = next(get_db())

        if message.from_user.is_bot:
            await message.answer("❌ ربات ها نمیتوانند از این ربات استفاده کنند ❌")
        
        # Get or create user based on mode
        if config.MODE == "DEV":
            # Development mode - create user if not exists with admin privileges
            user = UserService.get_or_create_user(
                db=db,
                telegram_id=str(message.from_user.id),
                username=message.from_user.username,
                is_admin=True,
            )
            if not user:
                await message.answer("❌ خطا در ایجاد کاربر")
                return
        else:
            # Production mode - only allow existing users
            user = UserService.get_user(
                db=db,
                user_tID=str(message.from_user.id),
                username=message.from_user.username,
            )

            if not user:
                await message.answer(
                    "❌ حساب کاربری شما پیدا نشد !\n\n"
                    "احتمالا حساب شما مجوز استفاده از این سرویس رو ندارد"
                )
                return
        
        # Create keyboard for main menu
        try:
            keyboard = get_main_menu_keyboard(chat_type=ChatType.PRIVATE, is_admin=user.is_admin)
        except Exception:
            logger.exception("error occurred in creating keyboard buttons")
            await message.answer("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
            return

        # Send welcome message with keyboard
        await message.answer(
            f"سلام {message.from_user.first_name}! به ربات مدیریت تسک خوش آمدید.\n"
            "شما به عنوان ادمین ثبت شدید.",
            reply_markup=keyboard
        )       
    
    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            await message.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Ensure database connection is closed
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

# ===== Start in Group or Supergroup chat =====
@router.message(Command("start"), chat_type_filter(ChatType.GROUP))
@router.message(Command("start"), chat_type_filter(ChatType.SUPERGROUP))
async def cmd_start_group(message: Message):
    """Handle /start command in groups and supergroups"""
    try:
        db = next(get_db())
        
        # Check if user is admin or owner of the group
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )
        
        is_admin = chat_member.status in ['administrator', 'creator']
        
        if not is_admin:
            await message.answer("❌ فقط ادمین‌ها یا مالک گروه می‌توانند ربات را راه اندازی کنند.")
            return
        
        # Get or create user based on mode
        if config.MODE == "DEV":
            # Development mode
            user = UserService.get_or_create_user(
                db=db, 
                telegram_id=str(message.from_user.id),
                username=message.from_user.username,
                is_admin=True
            )
        
        else:
            # Production mode - only allow existing admin users
            user = UserService.get_user(
                db=db,
                user_tID=str(message.from_user.id),
                username=message.from_user.username,
            )

            if not user or not user.is_admin:
                await message.answer(
                    "❌ شما دسترسی به اجرای این عملیات ندارید"
                )
                return

        # Create or get group record
        group = TaskService.get_or_create_group(db, telegram_group_id=str(message.chat.id), name=message.chat.title)
        if not group:
            logger.exception("error occurred in creating group")
            await message.answer("❌خطایی در پیدا کردن گروه رخ داد. لطفاً دوباره تلاش کنید.")
            return
        
        # Create topic if user is in Supergroup
        if message.chat.type == "supergroup" and (topicID := message.message_thread_id):
            topic = TaskService.get_or_create_topic(db, telegram_topic_id=topicID, group_id=group.id)
            if not topic:
                logger.exception("error occurred in creating group")
                await message.answer("❌خطایی در پیدا کردن تاپیک رخ داد. لطفاً دوباره تلاش کنید.")
                return
        
        # Create group-specific keyboard
        try:
            keyboard = get_main_menu_keyboard(chat_type=ChatType.GROUP)
        except Exception:
            logger.exception("error occurred in creating keyboard buttons")
            await message.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
            return
        
        # Send success message
        await message.answer(
            f"✅ ربات با موفقیت راه اندازی شد!\n"
            f"گروه {message.chat.title} ثبت شد.\n"
            f"شما به عنوان ادمین ثبت شدید.",
            reply_markup=keyboard
        )
        
    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            await message.answer("❌خطایی در راه اندازی ربات رخ داد.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Ensure database connection is closed
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")