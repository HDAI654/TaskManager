from aiogram import F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ChatType
from database import get_db
from models import User, Task, UserTask
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from logger import logger
import asyncio
from . import main_router as router
from services.services import TaskService, UserService
from datetime import datetime

# ===== Create Callback Function ======
def get_callback(callback_query, new_callback_data):
    class SimpleCallback:
        def __init__(self, original_callback, data):
            self.message = original_callback.message
            self.data = data
            self.from_user = original_callback.from_user
            self.id = original_callback.id
        
        async def answer(self, *args, **kwargs):
            pass  # Do nothing for answer in mock
    
    mock_callback = SimpleCallback(callback_query, new_callback_data)
    return mock_callback

# ====== Tasks Menu ======
@router.message(F.text == "مدیریت تسک های من")
async def manage_my_tasks(message: Message, state: FSMContext=None, user_id=None, callback_query: CallbackQuery = None):
    """Handle manage my tasks button (private chat only)"""
    try:
        if message.chat.type != ChatType.PRIVATE:
            await message.answer("❌ این دستور فقط در چت خصوصی با ربات قابل استفاده است.")
            return
        db = next(get_db())

        if state:
            await state.update_data(user_message_id=message.message_id)
        
        # Find user
        target_user_id = user_id or message.from_user.id
        print(user_id)
        print(message.from_user.id)
        user = UserService.get_user(db=db, user_id=target_user_id)
        print(user)
        
        if not user:
            await message.answer("❌ کاربر یافت نشد. لطفاً ابتدا /start را بزنید.")
            return
        
        # Find tasks where user is admin
        tasks = TaskService.get_task_by_admin_id(db=db, admin_id=user.id)
        
        if not tasks:
            if not callback_query:
                await message.answer("📝 شما هیچ تسکی ایجاد نکرده‌اید.")
            else:
                await callback_query.message.edit_text("📝 شما هیچ تسکی ایجاد نکرده‌اید.")
            return
        
        # Create inline buttons for each task
        keyboard_buttons = []
        for task in tasks:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=task.title,
                    callback_data=f"view_task|{task.id}"
                )
            ])
        
        # Add back button
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main_menu")
        ])
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        if not callback_query:
            await message.answer(
                f"✅ تسک‌های شما: @{user.username}\n\n"
                "برای مدیریت هر تسک روی آن کلیک کنید:",
                reply_markup=inline_keyboard
            )
        else:
            await callback_query.message.edit_text(
                f"✅ تسک‌های شما: @{user.username}\n\n"
                "برای مدیریت هر تسک روی آن کلیک کنید:",
                reply_markup=inline_keyboard
            )
            await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error managing tasks: {e}")
        await message.answer("❌ خطایی در نمایش تسک‌ها رخ داد.")
    finally:
        db.close()

# ====== Task View Menu ======
@router.callback_query(F.data.startswith("view_task|"))
async def handle_view_task(callback_query: CallbackQuery):
    """Handle view task callback"""    
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Create task management buttons
        keyboard_buttons = [
            [InlineKeyboardButton(text="🗑️ حذف تسک", callback_data=f"delete_task|{task.id}")],
            [InlineKeyboardButton(text="🔙 بازگشت به لیست تسک‌ها", callback_data="back_to_task_list")],
            [InlineKeyboardButton(text="👥 افزودن کاربر", callback_data=f"add_user|{task.id}")],
            [InlineKeyboardButton(text="👥 حذف کاربر", callback_data=f"del_users|{task.id}")],
            [InlineKeyboardButton(text="👥 کاربران", callback_data=f"view_task_users|{task.id}")],
            [InlineKeyboardButton(text="⏰ ویرایش زمان شروع", callback_data=f"edit_start|{task.id}")],
            [InlineKeyboardButton(text="⏰ ویرایش زمان پایان", callback_data=f"edit_end|{task.id}")],
            [InlineKeyboardButton(text="📝 ویرایش توضیحات", callback_data=f"edit_desc|{task.id}")],
            [InlineKeyboardButton(text="📋 ویرایش نام", callback_data=f"edit_name|{task.id}")],
        ]
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit previous message
        await callback_query.message.edit_text(
            f"📋 تسک انتخاب شده: {task.title}\n\n"
            f"📝 توضیحات: {task.description or 'بدون توضیح'}\n"
            f"📅 شروع: {task.start_date.strftime('%Y-%m-%d') if task.start_date else 'تعیین نشده'}\n"
            f"📅 پایان: {task.end_date.strftime('%Y-%m-%d') if task.end_date else 'تعیین نشده'}\n"
            f"🔧 وضعیت: {task.status}\n\n"
            "عملیات ها:",
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error viewing task: {e}")
        await callback_query.answer("❌ خطا در نمایش تسک")
    finally:
        db.close()

# ====== Back To Task Menu ======
@router.callback_query(F.data == "back_to_task_list")
async def handle_back_to_task_list(callback_query: CallbackQuery):
    """Handle back to task list callback"""
    try:
        # First find the user based on the task or message
        db = next(get_db())
        
        # Get user from the original message or find another way
        # This is a temporary workaround - you might need to store user_id in callback data
        user = UserService.get_user(db=db, user_id=callback_query.from_user.id)

        
        if not user:
            await callback_query.answer("❌ کاربر یافت نشد")
            return
        
        # Create a new message to call manage_my_tasks properly
        await manage_my_tasks(
            message=callback_query.message,
            user_id=user.id,
            callback_query = callback_query
        )
        
    except Exception as e:
        logger.error(f"Error going back to task list: {e}")
        await callback_query.answer("❌ خطا در بازگشت")
    finally:
        db.close()

# ====== Delete Task ======
@router.callback_query(F.data.startswith("delete_task|"))
async def handle_delete_task(callback_query: CallbackQuery):
    """Handle delete task callback"""
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            # Return to task list if task not found
            await handle_back_to_task_list(callback_query)
            return
        
        task_title = task.title
        
        # Delete task
        res = TaskService.delete_task(db=db, task=task)
        if not res:
            await callback_query.answer("❌ خطا در حذف تسک")

        await callback_query.answer(f"✅ حذف شد {task_title} تسک")
        
        # Wait a moment and then return to task list
        await asyncio.sleep(1.0)
        await handle_back_to_task_list(callback_query)
        
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        await callback_query.answer("❌ خطا در حذف تسک")
    finally:
        db.close()

# ====== Back To Chat ======
@router.callback_query(F.data == "back_to_main_menu")
async def handle_back_to_main_menu(callback_query: CallbackQuery, state: FSMContext):
    """Handle back to main menu callback"""
    try:
        # Delete the current message
        await callback_query.message.delete()

        data = await state.get_data()
        user_message_id = data.get('user_message_id')
        
        if user_message_id:
            try:
                # Delete user's original message
                await callback_query.bot.delete_message(
                    chat_id=callback_query.message.chat.id,
                    message_id=user_message_id
                )
            except Exception as e:
                logger.error(f"Error deleting user message: {e}")
        
    except Exception as e:
        logger.error(f"Error going back to main menu: {e}")
        await callback_query.answer("❌ خطا در بازگشت")


# ====== Add User States ======
class AddUserStates(StatesGroup):
    waiting_for_username = State()

# ====== Add User to Task ======
@router.callback_query(F.data.startswith("add_user|"))
async def handle_add_user(callback_query: CallbackQuery, state: FSMContext):
    """Handle add user to task callback"""    
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
        
        # Get suggested users from group if task has a group
        suggested_users = []
        if task.group_id:
            group_users = db.query(User).filter(User.group_id == task.group_id).all()
            suggested_users = [user.username for user in group_users if user.username != "unknown"]
        
        # Create inline keyboard with suggested users
        keyboard_buttons = []
        
        # Add suggested users as buttons
        if suggested_users:
            for username in suggested_users[:8]:  # Limit to 8 users to avoid too many buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"👤 {username}",
                        callback_data=f"select_user|{username}"
                    )
                ])
        
        # Add manual input option
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="📝 وارد کردن دستی یوزرنیم",
                callback_data="manual_user_input"
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
        
        if suggested_users:
            message_text += "✅ کاربران پیشنهادی از گروه:\n"
            for username in suggested_users:
                message_text += f"• @{username}\n"
            message_text += "\n"
        
            message_text += "می‌توانید از کاربران پیشنهادی انتخاب کنید یا یوزرنیم را دستی وارد نمایید."
        
        await callback_query.message.edit_text(
            message_text,
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in add user menu: {e}")
        await callback_query.answer("❌ خطا در نمایش منوی افزودن کاربر")
    finally:
        db.close()

@router.callback_query(F.data.startswith("select_user|"))
async def handle_select_user(callback_query: CallbackQuery, state: FSMContext):
    """Handle user selection from suggested users"""
    try:
        username = callback_query.data.split("|")[1]

        data = await state.get_data()
        task_id = int(data.get('task_id'))
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        db = next(get_db())
        
        # Find or create user
        user = UserService.get_or_create_user(username=username)
        if not user:
            await callback_query.answer("❌ خطا در پیدا کردن کاربر")
                
        # Assign user to task
        res = UserService.assign_user_to_task(db, user.id, task_id)
        if not res:
            await callback_query.answer("❌  خطا در افزودن کاربر به تسک")
        
        await callback_query.answer(f"✅ کاربر @{username} اضافه شد")
        
        # Clear state
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error selecting user: {e}")
        await callback_query.answer("❌ خطا در افزودن کاربر")
    finally:
        db.close()

@router.callback_query(F.data == "manual_user_input")
async def handle_manual_user_input(callback_query: CallbackQuery, state: FSMContext):
    """Handle manual username input request"""
    try:
        data = await state.get_data()
        task_id = data.get('task_id')
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        # Edit message to request username input
        await callback_query.message.edit_text(
            "📝 لطفاً یوزرنیم کاربر را وارد کنید (بدون @):\n\n"
            "مثال: username123\n\n"
            "یا برای بازگشت /cancel را بزنید",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت",
                        callback_data=f"add_user|{task_id}"
                    )
                ]]
            )
        )
        
        # Set state to wait for username
        await state.set_state(AddUserStates.waiting_for_username)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in manual input request: {e}")
        await callback_query.answer("❌ خطا در درخواست ورود دستی")

@router.message(AddUserStates.waiting_for_username)
async def handle_username_input(message: Message, state: FSMContext):
    """Handle username input from user"""
    try:
        data = await state.get_data()
        task_id = int(data.get('task_id'))
        callback_message_id = data.get('callback_message_id')
        if message.text == "/cancel":            
            # Delete user's cancel message
            await message.delete()
            
            # Edit original message back to add user menu
            if task_id and callback_message_id:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=callback_message_id,
                    text=f"❌ خطا در افزودن کاربر",
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
            return
        
        username = message.text.strip()
        
        # Validate username
        if not username or len(username) > 32:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=callback_message_id,
                text=f"❌ خطا در پردازش یوزرنیم",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔙 بازگشت به تسک",
                            callback_data=f"view_task|{task_id}"
                        )
                    ]]
                )
            )
            return
        
        data = await state.get_data()
        task_id = int(data.get('task_id'))
        callback_message_id = data.get('callback_message_id')
        
        if not task_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=callback_message_id,
                text="❌ اطلاعات تسک یافت نشد",
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
            return
        
        db = next(get_db())
        
        # Find or create user
        user = UserService.get_or_create_user(username=username)
        if not user:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=callback_message_id,
                text="❌ خطا در پیدا کردن کاربر",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔙 بازگشت به تسک",
                            callback_data=f"view_task|{task_id}"
                        )
                    ]]
                )
            )
        
        # Assign user to task
        res = UserService.assign_user_to_task(db, user.id, task_id)
        if not res:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=callback_message_id,
                text="❌  خطا در افزودن کاربر به تسک",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="🔙 بازگشت به تسک",
                            callback_data=f"view_task|{task_id}"
                        )
                    ]]
                )
            )
        
        # Delete user's input message
        await message.delete()
        
        # Edit original message to show success
        if callback_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=callback_message_id,
                    text=f"✅ کاربر @{username} با موفقیت اضافه شد!",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="🔙 بازگشت به تسک",
                                callback_data=f"view_task|{task_id}"
                            )
                        ]]
                    )
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                # Fallback: send success message
                await message.answer(f"✅ کاربر @{username} اضافه شد!")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error processing username input: {e}")
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=callback_message_id,
            text=f"❌ خطا در پردازش یوزرنیم",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🔙 بازگشت به تسک",
                        callback_data=f"view_task|{task_id}"
                    )
                ]]
            )
        )
    finally:
        db.close()

# ====== View Task Users ======
@router.callback_query(F.data.startswith("view_task_users|"))
async def handle_view_task_users(callback_query: CallbackQuery):
    """Handle view task users callback - display users assigned to a task"""    
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

        admin_user = UserService.get_user(db=db, user_id=task.admin_id)
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
        
    except Exception as e:
        logger.error(f"Error viewing task users: {e}")
        await callback_query.answer("❌ خطا در نمایش کاربران تسک")
    finally:
        db.close()


# ====== Delete User States ======
class DeleteUserStates(StatesGroup):
    waiting_for_user_selection = State()

# ====== Delete User from Task ======
@router.callback_query(F.data.startswith("del_users|"))
async def handle_delete_user_menu(callback_query: CallbackQuery, state: FSMContext):
    """Handle delete user from task menu callback"""
    try:
        task_id = int(callback_query.data.split("|")[1])

        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        # Get all users assigned to this task
        assigned_users = TaskService.get_task_users(db=db, task_id=task_id)
        
        if not assigned_users:
            await callback_query.answer("⚠️ هیچ کاربری در این تسک وجود ندارد")
            return
        
        # Store task info in state
        await state.update_data(
            task_id=task_id,
            callback_message_id=callback_query.message.message_id,
            assigned_users=[user.id for user in assigned_users]
        )
        
        # Create inline keyboard with users to delete
        keyboard_buttons = []
        
        # Add users as buttons
        for user in assigned_users[:10]:  # Limit to 10 users to avoid too many buttons
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"❌ حذف {user.username}",
                    callback_data=f"delete_user_confirm|{user.id}"
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
        
        # Edit message to show user selection for deletion
        await callback_query.message.edit_text(
            f"🗑️ حذف کاربر از تسک: {task.title}\n\n"
            "لطفاً کاربری که می‌خواهید حذف کنید را انتخاب کنید:",
            reply_markup=inline_keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in delete user menu: {e}")
        await callback_query.answer("❌ خطا در نمایش منوی حذف کاربر")
    finally:
        db.close()

@router.callback_query(F.data.startswith("delete_user_confirm|"))
async def handle_delete_user_confirm(callback_query: CallbackQuery, state: FSMContext):
    """Handle user deletion confirmation"""
    try:
        user_id_to_delete = int(callback_query.data.split("|")[1])

        data = await state.get_data()
        task_id = int(data.get('task_id'))
        assigned_users = data.get('assigned_users', [])
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        # Verify the user is actually assigned to this task
        if user_id_to_delete not in assigned_users:
            await callback_query.answer("❌ کاربر در این تسک وجود ندارد")
            return
        
        db = next(get_db())
        
        # Get user and task info for display
        user_to_delete = UserService.get_user(db=db, user_id=user_to_delete)
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not user_to_delete or not task:
            await callback_query.answer("❌ اطلاعات یافت نشد")
            return
        
        # Create confirmation keyboard
        keyboard_buttons = [
            [
                InlineKeyboardButton(
                    text="✅ بله، حذف کن",
                    callback_data=f"delete_user_final|{user_id_to_delete}"
                ),
                InlineKeyboardButton(
                    text="❌ خیر، بازگشت",
                    callback_data=f"view_task|{task_id}"
                )
            ]
        ]
        
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Edit message to show confirmation
        await callback_query.message.edit_text(
            f"⚠️ حذف کنید ؟ '{task.title}' را از تسک '{user_to_delete.username}' آیا مطمئن هستید که می‌خواهید کاربر",
            reply_markup=inline_keyboard
        )
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in delete user confirmation: {e}")
        await callback_query.answer("❌ خطا در تأیید حذف کاربر")
    finally:
        db.close()

@router.callback_query(F.data.startswith("delete_user_final|"))
async def handle_delete_user_final(callback_query: CallbackQuery, state: FSMContext):
    """Handle final user deletion"""
    user_id_to_delete = int(callback_query.data.split("|")[1])
    
    try:
        data = await state.get_data()
        task_id = int(data.get('task_id'))
        
        if not task_id:
            await callback_query.answer("❌ اطلاعات تسک یافت نشد")
            return
        
        db = next(get_db())
        
        # Get user and task info for display
        user_to_delete = UserService.get_user(db=db, user_id=user_to_delete)
        task = TaskService.get_task_by_id(db=db, id=task_id)
        
        if not user_to_delete or not task:
            await callback_query.answer("❌ اطلاعات یافت نشد")
            return
        
        # Delete the user from task
        res = TaskService.delete_user_from_task(db=db, task_id=task_id, user_id=user_id_to_delete)

        # Return to task view
        mock_callback = get_callback(callback_query, f"view_task|{task_id}")
        
        if res:            
            await callback_query.answer(f"✅ کاربر @{user_to_delete.username} حذف شد")
            
            # Call handle_view_task directly
            await handle_view_task(mock_callback)

            # Clear state
            await state.clear()
        
        elif res == "NOT_EXIST":
            await callback_query.answer("❌ کاربر در این تسک وجود ندارد")

            # Call handle_view_task directly
            await handle_view_task(mock_callback)

            # Clear state
            await state.clear()
            
            return
            
            
        else:
            await callback_query.answer("❌ خطا در حذف کاربر")

            # Call handle_view_task directly
            await handle_view_task(mock_callback)

            # Clear state
            await state.clear()

            return
            
    except Exception as e:
        logger.error(f"Error deleting user from task: {e}")
        await callback_query.answer("❌ خطا در حذف کاربر")
    finally:
        db.close()

# ====== Edit Task States ======
class EditTaskStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_start = State()
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

    except Exception as e:
        logger.exception(f"Error in handle_edit_name: {e}")
        await callback_query.answer("❌ خطا در تغییر نام")
    finally:
        if db:
            db.close()

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

    except Exception as e:
        logger.exception(f"Error in process_edit_name: {e}")
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
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")
    finally:
        if db:
            db.close()


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

    except Exception as e:
        logger.exception(f"Error in handle_edit_desc: {e}")
        await callback_query.answer("❌ خطا در تغییر توضیحات")
    finally:
        if db:
            db.close()

@router.message(EditTaskStates.waiting_for_desc)
async def process_edit_desc(message: Message, state: FSMContext):
    db = None
    try:
        new_des = message.text.strip()
        data = await state.get_data()
        task_id = int(data.get("task_id"))
        prompt_msg_id = data.get("prompt_msg_id")

        db = next(get_db())
        res = TaskService.edit_task(db=db, task_id=task_id, name=new_des)

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

    except Exception as e:
        logger.exception(f"Error in process_edit_name: {e}")
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
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")
    finally:
        if db:
            db.close()

# ====== Edit Task End Date ======
@router.callback_query(F.data.startswith("edit_end|"))
async def handle_edit_end(callback_query: CallbackQuery, state: FSMContext):
    db = None
    try:
        task_id = int(callback_query.data.split("|")[1])
        db = next(get_db())
        task = TaskService.get_task_by_id(db=db, id=task_id)

        if not task:
            await callback_query.answer("❌ تسک یافت نشد")
            return
        
        await state.update_data(task_id=task_id, prompt_msg_id=callback_query.message.message_id)

        await state.set_state(EditTaskStates.waiting_for_end)
        
        await callback_query.message.edit_text(
            f"📝 تغییر تاریخ اتمام تسک: {task.title}\n\n"
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

    except Exception as e:
        logger.exception(f"Error in handle_edit_end: {e}")
        await callback_query.answer("❌ خطا در تغییر تاریخ اتمام")
    finally:
        if db:
            db.close()


@router.message(EditTaskStates.waiting_for_end)
async def process_edit_end(message: Message, state: FSMContext):
    date_text = message.text.strip()
    data = await state.get_data()
    task_id = int(data.get("task_id"))
    callback_message_id = data.get("callback_message_id")
    prev_error_msg_id = data.get("error_message_id")

    try:
        new_end = datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        # حذف پیام کاربر
        try:
            await message.delete()
        except Exception:
            logger.exception("Could not delete user message (invalid date)")

        # حذف پیام ارور قبلی اگر هست
        if prev_error_msg_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_error_msg_id)
            except Exception:
                logger.exception("Could not delete previous error message (invalid date)")

        # ارسال پیام ارور جدید و ذخیره id آن
        try:
            err_msg = await message.answer("❌ فرمت تاریخ اشتباه است. دوباره وارد کنید (YYYY-MM-DD).")
            await state.update_data(error_message_id=err_msg.message_id)
        except Exception:
            logger.exception("Could not send new error message (invalid date)")

        return

    db = None
    try:
        db = next(get_db())
        res = TaskService.edit_task(db=db, task_id=task_id, name=date_text)

        if res:
            text = "✅ توضیحات تسک تغییر کرد"
        elif res == "NOT_EXIST":
            text = "❌ این تسک وجود ندارد"
        else:
            text = "❌ مشکلی در تغییر تسک به وجود آمد"

    except Exception:
        logger.exception("DB error while updating end_date")
        await message.answer("❌ خطا در ذخیره‌سازی تاریخ")
        await state.clear()
        return

    finally:
        if db:
            try:
                db.close()
            except Exception:
                logger.exception("Error closing DB session in process_edit_end")

    # حذف پیام کاربر
    try:
        await message.delete()
    except Exception:
        logger.exception("Could not delete user message after success")

    # حذف پیام ارور قبلی
    if prev_error_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_error_msg_id)
        except Exception:
            logger.exception("Could not delete previous error message after success")

    # ویرایش پیام اولیهٔ ربات به متن موفقیت + دکمه بازگشت
    if callback_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=callback_message_id,
                text="✅ زمان پایان تسک تغییر کرد",
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
            logger.exception("Could not edit callback message to success for end date")
            try:
                await message.answer(
                    "✅ زمان پایان تسک تغییر کرد",
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
                logger.exception("Could not send fallback success message for end date")

    await state.clear()
