from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command
from .. import admin_require, del_message, get_callback
from .. import main_router as router
from database import get_db
from logger import logger
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.task_services import TaskService, TaskAttachmentService
from services.user_services import UserService
from typing import Tuple, List
from ..funcs import exception_decorator
from aiogram import F
import asyncio
import datetime
from aiogram.exceptions import TelegramBadRequest
from models import User


@exception_decorator
def chunk_list(lst:list, chunk_size: int) -> List[List] | None:
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def task_manage_keyboard(db) -> Tuple[List[str], InlineKeyboardMarkup]:
    text = []
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    groups = TaskService.get_all_groups(db=db)
    if groups is None:
        text.append("⚠️ هیچ تاپیکی برای نمایش وجود ندارد ⚠️")
        tasks = TaskService.get_all_tasks(db=db)
        if tasks is None:
            text.append("⚠️ هیچ تسکی برای نمایش وجود ندارد ⚠️")
        else:
            text.append(f"تسک ها : \n تعداد: {len(groups)}")
            keyboard.inline_keyboard.extend(
                [
                    [InlineKeyboardButton(text=b.title, callback_data=f"view_task|{b.id}") for b in c]
                    for c in chunk_list(tasks, 2)
                ]
            )
    else:
        text.append(f"گروه ها : \n تعداد: {len(groups)}")
        keyboard.inline_keyboard.extend(
            [
                [InlineKeyboardButton(text=b.name, callback_data=f"view_group|{b.id}") for b in c]
                for c in chunk_list(groups, 2)
            ]
        )
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="سایر ...", callback_data=f"view_group|OTHER")]
        )

    return text, keyboard


# ===== Handler for show group's tasks =====
@router.callback_query(F.data.startswith("view_group|"))
async def handle_view_group_tasks(callback_query: CallbackQuery):
    db = None
    try:
        # Get database session
        db = next(get_db())

        # Extract group's ID
        try:
            group_ID = callback_query.data.split("|")[1]
            if group_ID != "OTHER":
                group_ID = int(group_ID)
                group = TaskService.get_group(db=db, id=group_ID)
                if group is None:
                    await callback_query.answer("❌ مشکلی در پیدا کردن این گروه به وجود آمد")
            else:
                group = None
                group_ID = False
        except Exception:
            logger.exception("Failed to extract group's ID from callback_query")
            await callback_query.answer("❌ مشکلی در پیدا کردن این گروه به وجود آمد")
            return
        
        tasks = TaskService.get_all_tasks(db=db, group_id=group_ID)
        if not tasks:
            await callback_query.answer("⚠️ تسکی برای این گروه پیدا نشد ⚠️")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        keyboard.inline_keyboard.extend(
            [
                [InlineKeyboardButton(text=b.title, callback_data=f"view_task|{b.id}") for b in c]
                for c in chunk_list(tasks, 2)
            ]
        )
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="باز گشت 🔙", callback_data=f"back")]
        )
            
        
        await callback_query.message.edit_text(
            f"تسک های گروه {group.name}: \n" if group else "تسک ها \n"
            f"تعداد: {len(tasks)}\n\n",
            reply_markup=keyboard
        )
    
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Ensure database connection is always closed
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close database connection")


# ===== Handler for finish manage =====
@router.callback_query(F.data.startswith("finish_task_manage|"))
async def handle_view_group_tasks(callback_query: CallbackQuery):
    try:
        await callback_query.message.delete()
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   


# ===== Handler for manage tasks =====
@router.callback_query(F.data == "back")
@router.message(Command("tasks"))
async def handle_task_manage(event: Message | CallbackQuery):
    """Main handler for manage tasks"""
    db = None
    try:
        db = next(get_db())  # Open a database session        
        # Check admin permission before proceeding
        permission = await admin_require(db, event)
        if not permission:
            return
        
        text, keyboard = task_manage_keyboard(db=db)

        text="\n".join(text)
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text=text, reply_markup=keyboard)
        else:
            await event.answer(text=text, reply_markup=keyboard)
            await event.delete()
             
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            if isinstance(event, CallbackQuery):
                await event.message.edit_text(text=text, reply_markup=keyboard)
            else:
                await event.answer(text=text, reply_markup=keyboard)
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

# ====== Task View Menu ======
@router.callback_query(F.data.startswith("view_task|"))
@router.callback_query(F.data.startswith("show_task|"))
async def handle_view_task(callback_query: CallbackQuery, state: FSMContext = None):
    """Handle view task callback"""   
    db = None 
    try:
        show_type = callback_query.data.split("|")[0]
        task_id = int(callback_query.data.split("|")[1])
        if state:
            await state.clear()

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        admin = UserService.get_user(db, user_ID=task.admin_id)
        
        if not task or not admin:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Create task management buttons
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="back"),
                InlineKeyboardButton(text="🗑️ حذف تسک", callback_data=f"delete_task|{task.id}"),
            ],
            [
                InlineKeyboardButton(text="👥 افزودن کاربر", callback_data=f"add_user|{task.id}"), 
                InlineKeyboardButton(text="👥 حذف کاربر", callback_data=f"del_users|{task.id}")
            ],
            [
                InlineKeyboardButton(text="👥 کاربران", callback_data=f"view_task_users|{task.id}"),
                InlineKeyboardButton(text="⏰ ویرایش زمان پایان", callback_data=f"edit_end|{task.id}")
            ],
            [
                InlineKeyboardButton(text="📝 ویرایش توضیحات", callback_data=f"edit_desc|{task.id}"), 
                InlineKeyboardButton(text="📋 ویرایش نام", callback_data=f"edit_name|{task.id}")
            ],
            [
                InlineKeyboardButton(text="📝 افزودن اتچمنت", callback_data=f"add_attachment|{task.id}"), 
                InlineKeyboardButton(text="📝 دریافت اتچمنت", callback_data=f"get_attachments|{task.id}"), 
            ],
        ]

        if show_type == "show_task":
            keyboard_buttons = [
                [
                    InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_show"),
                ],
                [
                    InlineKeyboardButton(text="📝 دریافت اتچمنت", callback_data=f"get_attachments|{task.id}"), 
                ],
            ]

        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit previous message
        await callback_query.message.edit_text(
            f"📋 تسک انتخاب شده: {task.title}\n\n"
            f"سازنده : @{admin.username}\n"
            f"📝 توضیحات: {task.description or 'بدون توضیح'}\n"
            f"📅 شروع: {task.start_date.strftime('%Y-%m-%d') if task.start_date else 'تعیین نشده'}\n"
            f"📅 پایان: {task.end_date.strftime('%Y-%m-%d') if task.end_date else 'تعیین نشده'}\n"
            f"🔧 وضعیت: {task.status}\n\n"
            "عملیات ها:",
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

# ====== Delete Task ======
@router.callback_query(F.data.startswith("delete_task|"))
async def handle_delete_task(callback_query: CallbackQuery):
    """Handle delete task callback"""
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            # Return to task list if task not found
            await handle_task_manage(callback_query)
            return
        
        task_title = task.title
        
        # Delete task
        res = TaskService.delete_task(db=db, task=task)
        if not res:
            await callback_query.answer("❌ خطا در حذف تسک")

        await callback_query.answer(f"✅ حذف شد {task_title} تسک")
        
        # Return to task list
        await handle_task_manage(callback_query)
        
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")


# ====== Edit Task States ======
class EditTaskStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_end = State()


# ====== Edit Task Name ======
@router.callback_query(F.data.startswith("edit_name|"))
async def handle_edit_name(callback_query: CallbackQuery, state: FSMContext):
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])
        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)

        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        await state.update_data(task_id=task_id, prompt_msg_id=callback_query.message.message_id)

        await state.set_state(EditTaskStates.waiting_for_name)
        
        await callback_query.message.edit_text(
            f"📝 تغییر نام تسک: {task.title}\n\n"
            "لطفاً نام جدید را وارد کنید:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
        await callback_query.answer()

    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

@router.message(EditTaskStates.waiting_for_name)
async def process_edit_name(message: Message, state: FSMContext):
    db = None
    try:
        new_name = message.text.strip()
        data = await state.get_data()
        task_id = int(data.get("task_id"))
        prompt_msg_id = data.get("prompt_msg_id")

        db = next(get_db())
        res = TaskService.edit_task(db=db, task_id=task_id, name=new_name)

        # پیام کاربر پاک بشه
        await message.delete()

        if res:
            text = "✅ نام تسک تغییر کرد"
        elif res == "NOT_EXIST":
            text = "❌ این تسک وجود ندارد"
        else:
            text = "❌ مشکلی در تغییر تسک به وجود آمد"

        # پیام اصلی که قبلاً ذخیره کردیم تغییر کنه
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت به تسک",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
        
        await state.clear()

    except Exception:
        logger.exception("Unexpected error occurred")
        data = await state.get_data()
        task_id = data.get("task_id", "UNKNOWN")
        prompt_msg_id = data.get("prompt_msg_id", message.message_id - 1)

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_msg_id,
                text="❌ مشکلی در تغییر تسک به وجود آمد",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔙 بازگشت به تسک",
                            callback_data=f"view_task|{task_id}"
                        )
                    ]]
                )
            )
        except Exception:
            logger.exception(f"Failed to send error message")
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

# ====== Edit Task Description ======
@router.callback_query(F.data.startswith("edit_desc|"))
async def handle_edit_desc(callback_query: CallbackQuery, state: FSMContext):
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])
        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)

        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        await state.update_data(task_id=task_id, prompt_msg_id=callback_query.message.message_id)

        await state.set_state(EditTaskStates.waiting_for_desc)
        
        await callback_query.message.edit_text(
            f"📝 تغییر توضیحات تسک: {task.title}\n\n"
            "لطفاً توضیحات جدید را وارد کنید:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
        await callback_query.answer()

    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

@router.message(EditTaskStates.waiting_for_desc)
async def process_edit_desc(message: Message, state: FSMContext):
    db = None
    try:
        new_des = message.text.strip()
        data = await state.get_data()
        task_id = int(data.get("task_id"))
        prompt_msg_id = data.get("prompt_msg_id")

        db = next(get_db())
        res = TaskService.edit_task(db=db, task_id=task_id, description=new_des)

        # پیام کاربر پاک بشه
        await message.delete()

        if res:
            text = "✅ توضیحات تسک تغییر کرد"
        elif res == "NOT_EXIST":
            text = "❌ این تسک وجود ندارد"
        else:
            text = "❌ مشکلی در تغییر تسک به وجود آمد"

        # پیام اصلی که قبلاً ذخیره کردیم تغییر کنه
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت به تسک",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
        
        await state.clear()

    except Exception:
        logger.exception("Unexpected error occurred")
        data = await state.get_data()
        task_id = data.get("task_id", "UNKNOWN")
        prompt_msg_id = data.get("prompt_msg_id", message.message_id - 1)

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=prompt_msg_id,
                text="❌ مشکلی در تغییر تسک به وجود آمد",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔙 بازگشت به تسک",
                            callback_data=f"view_task|{task_id}"
                        )
                    ]]
                )
            )
        except Exception:
            logger.exception(f"Failed to send error message")
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")



# ====== Edit Task End Date ======
@router.callback_query(F.data.startswith("edit_end|"))
async def handle_edit_end(callback_query: CallbackQuery, state: FSMContext):
    """
    When user clicks 'edit_end|<task_id>', ask them for a new end date.
    """
    db = None
    try:
        # Extract task_id from callback data
        task_id = int(callback_query.data.split("|")[1])

        # Open DB session
        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)

        # If task does not exist
        if not task:
            await callback_query.answer("❌ Task not found")
            return
        
        # Save task_id and the message_id of the bot's message into FSM state
        await state.update_data(
            task_id=task_id,
            callback_message_id=callback_query.message.message_id
        )

        # Set FSM state to wait for user input (new end date)
        await state.set_state(EditTaskStates.waiting_for_end)
        
        # Ask user to enter new date
        await callback_query.message.edit_text(
            f"📝 تغییر تاریخ پایان تسک: {task.title}\n\n"
            "لطفاً تاریخ پایان جدید را وارد کنید (YYYY-MM-DD)",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 Back",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
        await callback_query.answer()

    except Exception:
        # Log and notify user if unexpected error happens
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message") 
    
    finally:
        # Always close DB session
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close DB session in handle_edit_end")

# ====== Process new end date ======
@router.message(EditTaskStates.waiting_for_end)
async def process_edit_end(message: Message, state: FSMContext):
    """
    Process user input (new end date) and update the task in DB.
    """
    db = None
    try:
        # Get text input from user
        date_text = message.text.strip()

        # Retrieve state data
        data = await state.get_data()
        task_id = int(data.get("task_id"))
        callback_message_id = data.get("callback_message_id")
        prev_error_msg_id = data.get("error_message_id")

        # Try to parse date (YYYY-MM-DD)
        try:
            new_end = datetime.datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            # Delete user's wrong message
            try:
                await message.delete()
            except Exception:
                logger.exception("Could not delete invalid date message")

            # Delete previous error message (if exists)
            if prev_error_msg_id:
                try:
                    await message.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=prev_error_msg_id
                    )
                except Exception:
                    logger.exception("Could not delete previous error message")

            # Send new error message and store its id
            try:
                err_msg = await message.answer(
                    "❌ فرمت تاریخ اشتباه است. لطفاً دوباره وارد کنید (YYYY-MM-DD)."
                )
                await state.update_data(error_message_id=err_msg.message_id)
            except Exception:
                logger.exception("Could not send new error message")

            return

        # Update task in DB
        db = next(get_db())
        res = TaskService.edit_task(
            db=db,
            task_id=task_id,
            end_date=new_end
        )

        # Decide response text based on result
        if res:
            text = "✅ تاریخ پایان تسک با موفقیت تغییر کرد"
        elif res == "NOT_EXIST":
            text = "❌ تسک مورد نظر وجود ندارد"
        else:
            text = "❌ تغییر تاریخ پایان تسک با خطا مواجه شد"


        # Delete user's message (the date they typed)
        try:
            await message.delete()
        except Exception:
            logger.exception("Could not delete user message after success")

        # Delete old error message if any
        if prev_error_msg_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=prev_error_msg_id
                )
            except Exception:
                logger.exception("Could not delete previous error message after success")

        # Edit the original bot message with success info + back button
        if callback_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=callback_message_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="🔙 باز گشت",
                                callback_data=f"view_task|{task_id}"
                            )
                        ]]
                    )
                )
            except Exception:
                # If editing fails, send a new message as fallback
                logger.exception("Could not edit original message, sending fallback")
                try:
                    await message.answer(
                        text,
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[
                                InlineKeyboardButton(
                                    text="🔙 باز گشت",
                                    callback_data=f"view_task|{task_id}"
                                )
                            ]]
                        )
                    )
                except Exception:
                    logger.exception("Could not send fallback success message")

        # Clear FSM state
        await state.clear()

    except Exception:
        # Log and notify user if unexpected error happens
        logger.exception("Unexpected error occurred in process_edit_end")
        try:
            await message.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message in process_edit_end") 
    
    finally:
        # Always close DB session
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close DB session in process_edit_end")


# ====== Add User to Task ======
@router.callback_query(F.data.startswith("add_user|"))
async def handle_add_user(callback_query: CallbackQuery, state: FSMContext):
    """Handle add user to task callback"""   
    db = None 
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Store task info in state
        await state.update_data(
            task_id=task_id,
            callback_message_id=callback_query.message.message_id
        )
        
        # Get suggested users from database
        suggested_users = list(UserService.get_all_users(db, user_tID=callback_query.from_user.id, task_id=task_id))
        if len(suggested_users) == 0:
            await callback_query.answer("⚠️ کاربری برای نمایش وجود ندارد ⚠️")
            return
        
        if callback_query.message.chat.type in ("group", "supergroup"):
            try:
                # Get all chat members
                chat_members = await callback_query.message.bot.get_chat_administrators(callback_query.message.chat.id)
                group_users = [member.user for member in chat_members if not member.user.is_bot]

                group_users_ids = {user.id for user in group_users}
                suggested_users = [user.username for user in suggested_users if user.telegram_id in group_users_ids]

                if len(suggested_users) == 0:
                    await callback_query.answer("⚠️ کاربری برای نمایش وجود ندارد ⚠️")
                    return

            except Exception:
                logger.exception("Failed to fetch group members for suggested users")
                await callback_query.answer("❌ خطایی در پیدا کردن کاربران به وجود آمد")
                return
        else:
            suggested_users = [user.username for user in suggested_users]
        
        # Create inline keyboard with suggested users
        keyboard_buttons = []
        
        print(len(list(suggested_users)))
        # Add suggested users as buttons
        if len(list(suggested_users)) != 0:
            for username in suggested_users:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"👤 {username}",
                        callback_data=f"select_user|{username}"
                    )
                ])
        
        # Add back button
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🔙 بازگشت",
                callback_data=f"view_task|{task_id}"
            )
        ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit message to show user selection
        message_text = f"👥 افزودن کاربر به تسک: {task.title}\n\n"
        
        await callback_query.message.edit_text(
            message_text,
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

@router.callback_query(F.data.startswith("select_user|"))
async def handle_select_user(callback_query: CallbackQuery, state: FSMContext):
    """Handle user selection from suggested users"""
    try:
        username = callback_query.data.split("|")[1]

        data = await state.get_data()
        task_id_str = data.get('task_id')
        if not task_id_str:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        task_id = int(task_id_str)
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        db = next(get_db())
        
        # Find or create user
        user = UserService.get_or_create_user(db, username=username)
        if not user:
            await callback_query.answer("❌ خطا در پیدا کردن کاربر")
                
        # Assign user to task
        res = UserService.assign_user_to_task(db, user.id, task_id)
        if not res:
            await callback_query.answer("❌  خطا در افزودن کاربر به تسک")
        
        await callback_query.answer(f"✅ کاربر @{username} اضافه شد")
        
        # Clear state
        await state.clear()
        
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")


# ====== View Task Users ======
@router.callback_query(F.data.startswith("view_task_users|"))
async def handle_view_task_users(callback_query: CallbackQuery):
    """Handle view task users callback - display users assigned to a task"""    
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        
        # Get task information
        task = TaskService.get_task_by_id(db=db, id=task_id)
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Get all users assigned to this task
        assigned_users = TaskService.get_task_users(db=db, task_id=task_id)

        admin_user = UserService.get_user(db=db, user_ID=task.admin_id)
        if admin_user:
            task_admin_username = admin_user.username
        else:
            task_admin_username = "نامشخص"
        
        # Create message text
        if assigned_users:
            users_text = "👥 کاربران اختصاص داده شده به این تسک:\n\n"
            for i, user in enumerate(assigned_users, 1):
                users_text += f"{i}. {user.username}\n"
        else:
            users_text = "📝 هیچ کاربری به این تسک اختصاص داده نشده است."
        
        # Create back button
        keyboard_buttons = [
            [InlineKeyboardButton(text="🔙 بازگشت به تسک", callback_data=f"view_task|{task_id}")]
        ]
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit message to show users
        await callback_query.message.edit_text(
            f"📋 تسک: {task.title}\n\n"
            f"ادمین : {task_admin_username}\n"
            f"{users_text}",
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database connection
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")


# ====== Delete User States ======
class DeleteUserStates(StatesGroup):
    waiting_for_user_selection = State()  # State for waiting until a user is selected for deletion


# ====== Delete User from Task ======
@router.callback_query(F.data.startswith("del_users|"))
async def handle_delete_user_menu(callback_query: CallbackQuery, state: FSMContext):
    """Handle delete user from task menu callback"""
    db = None
    try:
        # Extract task ID from callback data
        task_id = int(callback_query.data.split("|")[1])

        # Open a database session
        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            # Task not found
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Get all users assigned to this task
        assigned_users = TaskService.get_task_users(db=db, task_id=task_id)
        
        if not assigned_users:
            # No users to delete
            await callback_query.answer("⚠️ هیچ کاربری در این تسک وجود ندارد")
            return
        
        # Store task info and assigned users in FSM state
        await state.update_data(
            task_id=task_id,
            callback_message_id=callback_query.message.message_id,
            assigned_users=[user.id for user in assigned_users]
        )
        
        # Create inline keyboard for user deletion
        keyboard_buttons = []
        
        # Add a button for each assigned user (limit 10 to avoid too many buttons)
        for user in assigned_users[:10]:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"❌ حذف {user.username}",
                    callback_data=f"delete_user_final|{user.id}"
                )
            ])
        
        # Add a back button to return to task view
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🔙 بازگشت",
                callback_data=f"view_task|{task_id}"
            )
        ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit the message to show the user selection menu
        try:
            await callback_query.message.edit_text(
                f"🗑️ حذف کاربر از تسک: {task.title}\n\n"
                "لطفاً کاربری که می‌خواهید حذف کنید را انتخاب کنید:",
                reply_markup=inline_keyboard
            )
        except TelegramBadRequest:
            # Telegram throws this if message content is unchanged
            pass
        except Exception:
            try:
                await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
            except Exception:
                logger.exception("Failed to send error message")
        
    except Exception:
        # Log any unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database session
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")

# ====== Final User Deletion ======
@router.callback_query(F.data.startswith("delete_user_final|"))
async def handle_delete_user_final(callback_query: CallbackQuery, state: FSMContext):
    """Handle final deletion of a selected user from a task"""
    user_id_to_delete = int(callback_query.data.split("|")[1])
    db = None
    try:
        # Get stored FSM state data
        data = await state.get_data()
        task_id = int(data.get('task_id'))
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        # Open a database session
        db = next(get_db())
        
        # Fetch user and task info for display
        user_to_delete = UserService.get_user(db=db, user_ID=user_id_to_delete)
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not user_to_delete or not task:
            await callback_query.answer("❌ اطلاعات یافت نشد")
            return
        
        # Attempt to delete the user from the task
        res = TaskService.delete_user_from_task(db=db, task_id=task_id, user_id=user_id_to_delete)

        # Prepare a mock callback for returning to task view
        mock_callback = get_callback(callback_query, f"view_task|{task_id}")
        
        if res:
            # Successful deletion
            await callback_query.answer(f"✅ کاربر @{user_to_delete.username} حذف شد")
            
            # Call view task handler to refresh the view
            await handle_view_task(mock_callback)

            # Clear FSM state
            await state.clear()
        
        elif res == "NOT_EXIST":
            # User was not part of this task
            await callback_query.answer("❌ کاربر در این تسک وجود ندارد")

            # Refresh task view
            await handle_view_task(mock_callback)

            # Clear FSM state
            await state.clear()
            return
            
        else:
            # Any other failure
            await callback_query.answer("❌ خطا در حذف کاربر")

            # Refresh task view
            await handle_view_task(mock_callback)

            # Clear FSM state
            await state.clear()
            return
            
    except Exception:
        # Log unexpected errors
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send error message")   
    
    finally:
        # Always close the database session
        if db is not None:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close db")            




# ====== Add Attachments to Task ======
@router.callback_query(F.data.startswith("add_attachment"))
async def handle_add_attachment(callback_query: CallbackQuery, state: FSMContext):
    """
    Start attachment adding mode for a task.
    After this, any file or supported message type will be stored as attachment.
    """
    try:
        # Extract task_id from callback_data
        # Format example: add_attachment|<task_id>
        task_id = int(callback_query.data.split("|")[1])

        # Store in state that we are adding attachments for this task
        await state.update_data(
            task_id=task_id,
            adding_attachments=True
        )

        # Edit current message to notify user
        await callback_query.message.edit_text(
            "📎 از این به بعد هر فایلی یا پیامی که ارسال کنید به عنوان اتچمنت اضافه می‌شود.\n"
            "برای پایان افزودن، دکمه بازگشت را فشار دهید.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )

        # Answer callback to remove "loading" state
        await callback_query.answer()

    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌ خطا رخ داد. دوباره تلاش کنید.")
        except Exception:
            logger.exception("Failed to send callback error message")


@router.message()
async def handle_new_attachment(message: Message, state: FSMContext):
    """
    Handle any new messages or files as attachments if the user is in 'adding_attachments' mode.
    """
    db = None
    try:
        data = await state.get_data()
        adding_attachments = data.get("adding_attachments", False)
        task_id = data.get("task_id")

        if not adding_attachments or not task_id:
            # Not in attachment adding mode
            return

        db = next(get_db())

        attachment_id = None

        # Determine attachment type
        if message.document:
            attachment_id = message.document.file_id
        elif message.photo:
            # For photo, take the highest resolution
            attachment_id = message.photo[-1].file_id
        elif message.video:
            attachment_id = message.video.file_id
        elif message.audio:
            attachment_id = message.audio.file_id
        elif message.voice:
            attachment_id = message.voice.file_id
        else:
            # You can extend for other message types
            return

        # Save attachment to database
        TaskAttachmentService.add_attachment(db=db, task_id=task_id, attachment_id=attachment_id)

        # Optionally notify user
        await message.answer("✅ فایل به عنوان اتچمنت اضافه شد")

    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            await message.answer("❌ خطا در افزودن فایل به اتچمنت")
        except Exception:
            logger.exception("Failed to send error message")
    
    finally:
        if db:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close DB session")


# ====== Send Attachments of Task to User ======
@router.callback_query(F.data.startswith("get_attachments|"))
async def handle_get_attachments(callback_query: CallbackQuery):
    """
    Send all attachments of a task to the same chat without editing the original message.
    Detect attachment type and use appropriate send method.
    """
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])
        db = next(get_db())

        # Get all attachments for the task
        attachments = TaskAttachmentService.get_attachments(db=db, task_id=task_id)

        if not attachments:
            await callback_query.answer("⚠️ هیچ اتچمنتی برای این تسک وجود ندارد", show_alert=True)
            return

        # Send each attachment using the correct method
        for attachment in attachments:
            file_id = attachment

            # Simple detection based on file_id prefix (Telegram file_id conventions)
            if file_id.startswith("AgAC"):  # likely photo/video (depends on your storage)
                await callback_query.message.bot.send_photo(
                    chat_id=callback_query.message.chat.id,
                    photo=file_id
                )
            else:
                await callback_query.message.bot.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=file_id
                )

        await callback_query.answer("✅ همه اتچمنت‌ها ارسال شدند", show_alert=True)

    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            await callback_query.answer("❌ خطا در ارسال اتچمنت‌ها", show_alert=True)
        except Exception:
            logger.exception("Failed to send error message")
    
    finally:
        if db:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close DB session")


# ====== Show user's tasks ======
async def handle_my_tasks(event: Message | CallbackQuery):
    """
    Show all tasks assigned to the current user with inline buttons.
    """
    db = None
    try:
        # Assuming telegram_id is unique for users
        telegram_id = event.from_user.id
        db = next(get_db())

        # Get the User object
        user = UserService.get_user(user_tID=telegram_id)
        if not user:
            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ شما در سیستم ثبت نشده‌اید", show_alert=True)
            else:
                await event.answer("⚠️ شما در سیستم ثبت نشده‌اید")
            return

        # Get tasks assigned to this user
        tasks = TaskService.get_tasks_for_user(db=db, user_id=user.id)
        if not tasks:
            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ هیچ تسکی برای شما وجود ندارد", show_alert=True)
            else:
                await event.answer("⚠️ هیچ تسکی برای شما وجود ندارد")
            return

        # Build inline keyboard
        keyboard_buttons = []
        for task in tasks:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=task.title,
                    callback_data=f"show_task|{task.id}"
                )
            ])
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        # Send message with tasks
        if isinstance(event, CallbackQuery):
            try:
                await event.message.edit_text(
                    "📋 تسک‌های شما:",
                    reply_markup=inline_keyboard
                )
            except TelegramBadRequest:
                # Telegram throws this if message content is unchanged
                pass
            except Exception:
                try:
                    await event.answer("❌خطایی رخ داد. لطفاً دوباره تلاش کنید.")
                except Exception:
                    logger.exception("Failed to send error message")
        else:
            await event.answer(
                "📋 تسک‌های شما:",
                reply_markup=inline_keyboard
            )

    except Exception:
        logger.exception("Unexpected error occurred")
        try:
            if isinstance(event, CallbackQuery):
                await event.answer("❌ خطا در دریافت تسک‌ها", show_alert=True)
            else:
                await event.answer("⚠️ هیچ تسکی برای شما وجود ندارد")
        except Exception:
            logger.exception("Failed to send error message")
    
    finally:
        if db:
            try:
                db.close()
            except Exception:
                logger.exception("Failed to close DB session")


@router.message(F.text == "تسک های من")
async def handle_my_tasks_message(message: Message):
    await handle_my_tasks(event=message)

@router.callback_query(F.data == "back_show")
async def handle_my_tasks_callback(callback: CallbackQuery):
    await handle_my_tasks(event=callback)