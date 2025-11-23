import os
import re
import asyncio
import logging
import threading
import fcntl
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
from main import main_with_params

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID", "")
ADMIN_USER_ID = None

if ADMIN_USER_ID_STR:
    try:
        ADMIN_USER_ID = int(ADMIN_USER_ID_STR.strip())
        logger.info(f"Admin user ID set: {ADMIN_USER_ID}")
    except ValueError:
        logger.error("Error parsing ADMIN_USER_ID. Please ensure it is an integer.")
        ADMIN_USER_ID = None

ALLOWED_USER_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = set()

if ALLOWED_USER_IDS_STR:
    try:
        ALLOWED_USER_IDS = {int(uid.strip()) for uid in ALLOWED_USER_IDS_STR.split(',') if uid.strip()}
        logger.info(f"Loaded {len(ALLOWED_USER_IDS)} allowed user IDs")
    except ValueError:
        logger.error("Error parsing ALLOWED_USER_IDS. Please ensure they are comma-separated integers.")
        ALLOWED_USER_IDS = set()

# If no allowed users specified, log warning (bot will be open to everyone)
if not ALLOWED_USER_IDS:
    logger.warning("⚠️  WARNING: No ALLOWED_USER_IDS set. Bot is accessible to everyone!")

# Conversation states
WAITING_FOR_TOPIC = 1
WAITING_FOR_FROM_DATE = 2
WAITING_FOR_TO_DATE = 3
WAITING_FOR_USER_ID_TO_ADD = 4
WAITING_FOR_USER_ID_TO_REMOVE = 5

# Store user data temporarily
user_sessions = {}


def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    # If no restrictions set, allow everyone
    if not ALLOWED_USER_IDS:
        return True
    
    return user_id in ALLOWED_USER_IDS


def is_admin(user_id: int) -> bool:
    """Check if user is the admin"""
    return ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID


def get_env_file_path() -> str:
    """Get the path to the .env file"""
    # Assuming .env is in the parent directory of the parser folder
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    return os.path.join(parent_dir, '.env')


def update_env_file(user_ids_set: set) -> bool:
    """Update the ALLOWED_USER_IDS in the .env file with file locking to prevent race conditions"""
    try:
        env_path = get_env_file_path()
        
        # Convert set to comma-separated string
        user_ids_str = ','.join(str(uid) for uid in sorted(user_ids_set))
        
        # Use file locking to prevent concurrent writes
        with open(env_path, 'r+') as f:
            # Acquire exclusive lock (blocks until available)
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            
            try:
                # Read existing content
                f.seek(0)
                env_lines = f.readlines()
                
                # Update existing ALLOWED_USER_IDS line
                found_allowed_users = False
                for i, line in enumerate(env_lines):
                    if line.strip().startswith('ALLOWED_USER_IDS='):
                        env_lines[i] = f'ALLOWED_USER_IDS={user_ids_str}\n'
                        found_allowed_users = True
                        break
                
                # If ALLOWED_USER_IDS not found, append it
                if not found_allowed_users:
                    if env_lines and not env_lines[-1].endswith('\n'):
                        env_lines.append('\n')
                    env_lines.append(f'ALLOWED_USER_IDS={user_ids_str}\n')
                
                # Write back to file
                f.seek(0)
                f.truncate()
                f.writelines(env_lines)
                f.flush()
                os.fsync(f.fileno())  # Ensure written to disk
                
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        # Update the global variable
        global ALLOWED_USER_IDS
        ALLOWED_USER_IDS = user_ids_set.copy()
        
        logger.info(f"Updated .env file with {len(user_ids_set)} user IDs")
        return True
        
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")
        return False


def validate_date_format(date_str: str) -> bool:
    """Validate date format YYYY.MM.DD using regex"""
    pattern = r'^\d{4}\.\d{2}\.\d{2}$'
    if not re.match(pattern, date_str):
        return False
    
    # Additional validation: check if date is valid
    try:
        year, month, day = date_str.split('.')
        datetime(int(year), int(month), int(day))
        return True
    except ValueError:
        return False


def convert_to_arxiv_format(from_date: str, to_date: str) -> str:
    """
    Convert user-friendly dates to arXiv format
    Input: YYYY.MM.DD format (e.g., "2025.10.01")
    Output: [YYYYMMDD0000+TO+YYYYMMDD2359] format
    """
    # Remove dots from dates
    from_date_clean = from_date.replace('.', '')
    to_date_clean = to_date.replace('.', '')
    
    # Add time components (midnight for start, end of day for end)
    start_time = f"{from_date_clean}0000"
    end_time = f"{to_date_clean}2359"
    
    return f"[{start_time}+TO+{end_time}]"


def start(update: Update, context: CallbackContext) -> int:
    """Start the conversation and ask for research topic"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    
    # Check if user is authorized
    if not is_user_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user_id: {user_id}, username: @{username}")
        update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "Sorry, you are not authorized to use this bot.\n\n"
            f"Your user ID: `{user_id}`\n\n"
            "Please contact the bot administrator if you believe this is an error.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    logger.info(f"Authorized user started session: {user_id} (@{username})")
    
    update.message.reply_text(
        "👋 *Welcome to arXiv Research Assistant!*\n\n"
        "I'll help you find and summarize recent research papers.\n\n"
        "🔍 *What research topic are you interested in?*\n\n"
        "Examples:\n"
        "- RAG\n"
        "- Transformer models\n"
        "- Computer vision\n"
        "- Reinforcement learning\n\n"
        "Just type your topic:",
        parse_mode="Markdown"
    )
    
    # Initialize session for this user
    user_sessions[user_id] = {}
    
    return WAITING_FOR_TOPIC


def receive_topic(update: Update, context: CallbackContext) -> int:
    """Receive the research topic from user"""
    user_id = update.effective_user.id
    topic = update.message.text.strip()
    
    # Store the topic
    user_sessions[user_id]['topic'] = topic
    
    update.message.reply_text(
        f"✅ *Topic received:* {topic}\n\n"
        f"📅 *Now let's set the date range.*\n\n"
        f"📆 *Enter the START date* in format: `YYYY.MM.DD`\n\n"
        f"Examples:\n"
        f"- `2025.08.01` (August 1, 2025)\n"
        f"- `2024.10.20` (October 20, 2024)\n\n"
        f"Please enter the start date:",
        parse_mode="Markdown"
    )
    
    return WAITING_FOR_FROM_DATE


def receive_from_date(update: Update, context: CallbackContext) -> int:
    """Receive and validate the FROM date"""
    user_id = update.effective_user.id
    from_date = update.message.text.strip()
    
    # Validate date format
    if not validate_date_format(from_date):
        update.message.reply_text(
            "❌ *Invalid date format!*\n\n"
            "Please use the format: `YYYY.MM.DD`\n\n"
            "Examples:\n"
            "- `2025.08.01`\n"
            "- `2024.10.20`\n\n"
            "Make sure:\n"
            "- Year is 4 digits\n"
            "- Month is 2 digits (01-12)\n"
            "- Day is 2 digits (01-31)\n"
            "- Separated by dots (`.`)\n\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_FROM_DATE
    
    # Store the from date
    user_sessions[user_id]['from_date'] = from_date
    
    update.message.reply_text(
        f"✅ *Start date received:* {from_date}\n\n"
        f"📆 *Now enter the END date* in format: `YYYY.MM.DD`\n\n"
        f"Examples:\n"
        f"- `2025.08.02` (August 2, 2025)\n"
        f"- `2024.10.24` (October 24, 2024)\n\n"
        f"Please enter the end date:",
        parse_mode="Markdown"
    )
    
    return WAITING_FOR_TO_DATE


def receive_to_date(update: Update, context: CallbackContext) -> int:
    """Receive and validate the TO date, then start processing"""
    user_id = update.effective_user.id
    to_date = update.message.text.strip()
    
    # Validate date format
    if not validate_date_format(to_date):
        update.message.reply_text(
            "❌ *Invalid date format!*\n\n"
            "Please use the format: `YYYY.MM.DD`\n\n"
            "Examples:\n"
            "- `2025.08.02`\n"
            "- `2024.10.24`\n\n"
            "Make sure:\n"
            "- Year is 4 digits\n"
            "- Month is 2 digits (01-12)\n"
            "- Day is 2 digits (01-31)\n"
            "- Separated by dots (`.`)\n\n"
            "Please try again:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_TO_DATE
    
    # Get the stored from_date and topic
    from_date = user_sessions[user_id]['from_date']
    topic = user_sessions[user_id]['topic']
    
    # Validate that to_date is after from_date
    from_dt = datetime.strptime(from_date, "%Y.%m.%d")
    to_dt = datetime.strptime(to_date, "%Y.%m.%d")
    
    if to_dt < from_dt:
        update.message.reply_text(
            "❌ *Invalid date range!*\n\n"
            f"End date ({to_date}) cannot be before start date ({from_date}).\n\n"
            "Please enter a valid end date:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_TO_DATE
    
    # Convert to arXiv format
    time_range = convert_to_arxiv_format(from_date, to_date)
    
    update.message.reply_text(
        f"🚀 *Starting research process!*\n\n"
        f"📌 Topic: {topic}\n"
        f"📅 Date Range: {from_date} to {to_date}\n"
        f"🔍 Searching: {time_range}\n\n"
        f"⏳ This may take a few minutes. I'll notify you when it's done!\n\n"
        f"Feel free to send /start again for a new search.",
        parse_mode="Markdown"
    )
    
    # Start the research process in a separate thread
    thread = threading.Thread(
        target=lambda: asyncio.run(process_research(user_id, topic, time_range, context))
    )
    thread.daemon = True
    thread.start()
    
    # End this conversation but keep bot running
    return ConversationHandler.END


async def process_research(user_id: int, topic: str, time_range: str, context: CallbackContext):
    """Process the research request asynchronously"""
    try:
        # Convert user_id to string for chat_id
        chat_id = str(user_id)
        
        # Run the main research function
        await main_with_params(topic, time_range, chat_id=chat_id)
        
        # Notify user that processing is complete via bot
        context.bot.send_message(
            chat_id=chat_id,
            text="✅ *Research complete!*\n\n"
                 "Check the messages above for your research digest.\n\n"
                 "Send /start to begin a new search!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in process_research: {e}")
        context.bot.send_message(
            chat_id=str(user_id),
            text=f"❌ *Error occurred during research:*\n\n"
                 f"`{str(e)}`\n\n"
                 f"Please try again with /start",
            parse_mode="Markdown"
        )
    finally:
        # Clean up session data
        if user_id in user_sessions:
            del user_sessions[user_id]


def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current conversation"""
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    update.message.reply_text(
        "❌ *Cancelled.*\n\n"
        "Send /start whenever you want to begin a new search!",
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END


def help_command(update: Update, context: CallbackContext):
    """Display help message"""
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if not is_user_authorized(user_id):
        update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "You are not authorized to use this bot.",
            parse_mode="Markdown"
        )
        return
    
    help_text = (
        "🤖 *arXiv Research Assistant Help*\n\n"
        "*Commands:*\n"
        "/start - Begin a new research search\n"
        "/cancel - Cancel current search setup\n"
        "/help - Show this help message\n"
    )
    
    # Add admin commands if user is admin
    if is_admin(user_id):
        help_text += (
            "\n*Admin Commands:*\n"
            "/add_user - Add a new authorized user\n"
            "/remove_user - Remove an authorized user\n"
            "/list_users - List all authorized users\n"
        )
    
    help_text += (
        "\n*How it works:*\n"
        "1. Send /start\n"
        "2. Enter your research topic (e.g., 'RAG', 'Transformers')\n"
        "3. Enter START date in format: `YYYY.MM.DD`\n"
        "4. Enter END date in format: `YYYY.MM.DD`\n"
        "5. Wait for results!\n\n"
        "*Date Format Examples:*\n"
        "- `2025.08.01` (August 1, 2025)\n"
        "- `2024.10.24` (October 24, 2024)\n\n"
        "The bot will search arXiv, parse papers, generate summaries, "
        "and send you a comprehensive research digest."
    )
    
    update.message.reply_text(help_text, parse_mode="Markdown")


def add_user_command(update: Update, context: CallbackContext) -> int:
    """Admin command to add a new user"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "This command is only available to administrators.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    update.message.reply_text(
        "👤 *Add New User*\n\n"
        "Please enter the Telegram User ID you want to authorize.\n\n"
        "💡 *Tip:* Users can find their ID by sending any message to @userinfobot\n\n"
        "Enter the user ID (numbers only):",
        parse_mode="Markdown"
    )
    
    return WAITING_FOR_USER_ID_TO_ADD


def receive_user_id_to_add(update: Update, context: CallbackContext) -> int:
    """Receive and process the user ID to add"""
    user_id = update.effective_user.id
    new_user_id_str = update.message.text.strip()
    
    # Validate that it's a number
    try:
        new_user_id = int(new_user_id_str)
    except ValueError:
        update.message.reply_text(
            "❌ *Invalid User ID*\n\n"
            "User ID must be a number.\n\n"
            "Please try again or send /cancel to abort:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_USER_ID_TO_ADD
    
    # Check if user is already authorized
    if new_user_id in ALLOWED_USER_IDS:
        update.message.reply_text(
            f"ℹ️ *User Already Authorized*\n\n"
            f"User ID `{new_user_id}` is already in the authorized users list.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Add user to the set
    updated_users = ALLOWED_USER_IDS.copy()
    updated_users.add(new_user_id)
    
    # Update .env file
    if update_env_file(updated_users):
        update.message.reply_text(
            f"✅ *User Added Successfully*\n\n"
            f"User ID `{new_user_id}` has been authorized.\n\n"
            f"Total authorized users: {len(updated_users)}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} added user {new_user_id}")
    else:
        update.message.reply_text(
            "❌ *Error*\n\n"
            "Failed to update the .env file. Please check the logs.",
            parse_mode="Markdown"
        )
    
    return ConversationHandler.END


def remove_user_command(update: Update, context: CallbackContext) -> int:
    """Admin command to remove a user"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "This command is only available to administrators.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    if not ALLOWED_USER_IDS:
        update.message.reply_text(
            "ℹ️ *No Users to Remove*\n\n"
            "There are currently no authorized users in the system.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    users_list = '\n'.join([f"• `{uid}`" for uid in sorted(ALLOWED_USER_IDS)])
    
    update.message.reply_text(
        f"👤 *Remove User*\n\n"
        f"Current authorized users:\n{users_list}\n\n"
        f"Please enter the User ID you want to remove:",
        parse_mode="Markdown"
    )
    
    return WAITING_FOR_USER_ID_TO_REMOVE


def receive_user_id_to_remove(update: Update, context: CallbackContext) -> int:
    """Receive and process the user ID to remove"""
    user_id = update.effective_user.id
    remove_user_id_str = update.message.text.strip()
    
    # Validate that it's a number
    try:
        remove_user_id = int(remove_user_id_str)
    except ValueError:
        update.message.reply_text(
            "❌ *Invalid User ID*\n\n"
            "User ID must be a number.\n\n"
            "Please try again or send /cancel to abort:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_USER_ID_TO_REMOVE
    
    # Check if user exists in the authorized list
    if remove_user_id not in ALLOWED_USER_IDS:
        update.message.reply_text(
            f"❌ *User Not Found*\n\n"
            f"User ID `{remove_user_id}` is not in the authorized users list.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Prevent admin from removing themselves
    if remove_user_id == ADMIN_USER_ID:
        update.message.reply_text(
            "⚠️ *Cannot Remove Admin*\n\n"
            "You cannot remove the admin user from the authorized list.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    
    # Remove user from the set
    updated_users = ALLOWED_USER_IDS.copy()
    updated_users.discard(remove_user_id)
    
    # Update .env file
    if update_env_file(updated_users):
        update.message.reply_text(
            f"✅ *User Removed Successfully*\n\n"
            f"User ID `{remove_user_id}` has been removed from authorized users.\n\n"
            f"Total authorized users: {len(updated_users)}",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {user_id} removed user {remove_user_id}")
    else:
        update.message.reply_text(
            "❌ *Error*\n\n"
            "Failed to update the .env file. Please check the logs.",
            parse_mode="Markdown"
        )
    
    return ConversationHandler.END


def list_users_command(update: Update, context: CallbackContext):
    """Admin command to list all authorized users"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if not is_admin(user_id):
        update.message.reply_text(
            "🚫 *Access Denied*\n\n"
            "This command is only available to administrators.",
            parse_mode="Markdown"
        )
        return
    
    if not ALLOWED_USER_IDS:
        update.message.reply_text(
            "ℹ️ *No Authorized Users*\n\n"
            "There are currently no authorized users in the system.\n"
            "The bot is accessible to everyone.",
            parse_mode="Markdown"
        )
        return
    
    users_list = '\n'.join([f"{i+1}. `{uid}`" for i, uid in enumerate(sorted(ALLOWED_USER_IDS))])
    
    update.message.reply_text(
        f"👥 *Authorized Users List*\n\n"
        f"Total: {len(ALLOWED_USER_IDS)} user(s)\n\n"
        f"{users_list}",
        parse_mode="Markdown"
    )


def main():
    """Start the bot"""
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env file")
        return
    
    # Display authorization info
    print("🔐 Authorization Configuration:")
    if ADMIN_USER_ID:
        print(f"   👑 Admin user ID: {ADMIN_USER_ID}")
    else:
        print("   ⚠️  WARNING: No admin user set (admin commands disabled)")
    
    if ALLOWED_USER_IDS:
        print(f"   ✅ Bot restricted to {len(ALLOWED_USER_IDS)} authorized user(s)")
        print(f"   Allowed user IDs: {sorted(ALLOWED_USER_IDS)}")
    else:
        print("   ⚠️  WARNING: Bot is OPEN to all users (no restrictions)")
        print("   To restrict access, set ALLOWED_USER_IDS in .env file")
    
    # Create the Updater and pass it your bot's token
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # Create conversation handler for main research flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_TOPIC: [
                MessageHandler(Filters.text & ~Filters.command, receive_topic)
            ],
            WAITING_FOR_FROM_DATE: [
                MessageHandler(Filters.text & ~Filters.command, receive_from_date)
            ],
            WAITING_FOR_TO_DATE: [
                MessageHandler(Filters.text & ~Filters.command, receive_to_date)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        # Allow multiple users to use the bot simultaneously
        per_user=True,
        per_chat=True,
    )
    
    # Create conversation handler for adding users (admin only)
    add_user_handler = ConversationHandler(
        entry_points=[CommandHandler("add_user", add_user_command)],
        states={
            WAITING_FOR_USER_ID_TO_ADD: [
                MessageHandler(Filters.text & ~Filters.command, receive_user_id_to_add)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )
    
    # Create conversation handler for removing users (admin only)
    remove_user_handler = ConversationHandler(
        entry_points=[CommandHandler("remove_user", remove_user_command)],
        states={
            WAITING_FOR_USER_ID_TO_REMOVE: [
                MessageHandler(Filters.text & ~Filters.command, receive_user_id_to_remove)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )
    
    # Add handlers
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(add_user_handler)
    dispatcher.add_handler(remove_user_handler)
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("list_users", list_users_command))
    
    # Start the bot
    print("🤖 Bot is starting...")
    print("👉 Send /start to your bot to begin!")
    
    # Run the bot until you press Ctrl-C
    updater.start_polling()
    
    # Run the bot until the user presses Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT
    updater.idle()


if __name__ == "__main__":
    main()

