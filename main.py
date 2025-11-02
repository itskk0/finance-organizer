import logging
import os
import json
import tempfile
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

import groq
from google_sheets_manager import GoogleSheetsManager
from transaction_processor import TransactionProcessor
from config import Config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Admin user IDs from environment
ADMIN_USER_IDS = set()
_admin_env = os.getenv('ADMIN_USER_IDS', '').strip()
if _admin_env:
    try:
        ADMIN_USER_IDS = {int(x) for x in _admin_env.split(',') if x.strip()}
    except Exception:
        ADMIN_USER_IDS = set()

# Groq API client
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is required")
groq_client = groq.Groq(api_key=GROQ_API_KEY)

# Service account email for Google Sheets access
SERVICE_ACCOUNT_EMAIL = os.getenv('SERVICE_ACCOUNT_EMAIL')
if not SERVICE_ACCOUNT_EMAIL:
    raise ValueError("SERVICE_ACCOUNT_EMAIL environment variable is required")

# Categories will be loaded dynamically from spreadsheet config
CATEGORIES = []

FINANCE_JSON_INSTRUCTIONS = (
    "You are a finance extraction assistant. Given a transcription of a voice note, "
    "extract structured fields and respond with ONLY valid JSON (no code fences, no text). "
    "Fields: {\n"
    "  \"type\": \"income\" or \"expense\",\n"
    "  \"category\": one string chosen ONLY from the provided categories list,\n"
    "  \"currency\": a 3-letter ISO currency code, only USD, EUR, RSD, RUB work, convert if needed\n"
    "  \"amount\": a number (use dot for decimals),\n"
    "  \"date\": ISO date (YYYY-MM-DD). If no date is explicitly mentioned, set to today's date. "
    "If a relative date (e.g., 'yesterday', 'three days ago') is mentioned in ANY language, "
    "resolve it relative to today and output the concrete ISO date.\n"
    "  \"month\": month name from the provided month names list,\n"
    "  \"comment\": free-text short description of the transaction,\n"
    "  \"source_text\": the original transcription\n"
    "}.\n"
    "If you are unsure about category, select the closest option from the list. "
    "If currency not specified but amount is present, infer from context if possible, else leave null. "
    "Always ensure valid JSON and include all fields."
)



class TelegramBot:
    def __init__(self):
        self.application = Application.builder().token(TOKEN).build()
        # Simple JSON storage for groups
        storage_file = os.getenv('FINANCE_BOT_STORAGE', 'groups.json')
        self.storage_path = Path(storage_file)
        self._ensure_storage()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup all command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("info", self.info_command))
        self.application.add_handler(CommandHandler("auth", self.auth_command))
        self.application.add_handler(CommandHandler("create", self.create_group_command))
        self.application.add_handler(CommandHandler("invite", self.invite_command))
        self.application.add_handler(CommandHandler("join", self.join_command))
        self.application.add_handler(CommandHandler("leave", self.leave_command))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        # Audio and voice handlers
        self.application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO) & ~filters.COMMAND, self.handle_audio_message))
        
        # Callback query handlers for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        welcome_message = (
            f"👋 Привет {user.first_name}!\n\n"
            "Добро пожаловать в бота для учета финансов!\n\n"
            "Отслеживайте доходы/расходы через текст или голос.\n\n"
            "Сначала создайте Google Таблицу и подключите к ней бота или присоединитесь к существующей Google Таблице для совместного ведения записей."
        )
        
        # Create inline keyboard
        keyboard = [
            [InlineKeyboardButton("🆕 Привязать бота к моей Google Таблице", callback_data="create_group")],
            [InlineKeyboardButton("🔗 Присоединиться как дополнительный пользователь", callback_data="join_group_prompt")],
            [InlineKeyboardButton("📋 Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
        logger.info(f"User {user.id} started the bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_text = (
            "🤖 **Доступные команды:**\n\n"
            "/start - Запустить бота и показать приветственное сообщение\n"
            "/help - Показать это сообщение помощи\n"
            "/info - Получить информацию о боте\n"
            "/auth - Админ: создать код; Пользователь: /auth <код> для авторизации\n"
            "/create <ссылка-на-таблицу> - Создать новую группу с Google Sheets\n"
            "/invite - Получить код приглашения для вашей группы\n"
            "/join <код> - Присоединиться к группе по коду приглашения\n"
            "/leave - Покинуть текущую группу (удаляет группу, если вы создатель)\n\n"
            "💡 **Возможности:**\n"
            "• Вы сами создаёте в *Google Таблице* именно те статьи бюджета, которые важны *именно вам* — свои категории доходов и расходов."
            "• Бот определяет эти категории и автоматически распределяет транзакции по ним."
            "• Можно вносить данные вручную в таблицу или отправлять через бота — он помогает делать это быстрее и удобнее."
            "• Голосовые сообщения и аудио автоматически транскрибируются и классифицируются как доход или расход и заносятся в вашу Google Таблицу."
            "• Полная *интеграция с Google Sheets* — данные обновляются в режиме реального времени."
            "• Возможность добавления пользователей и совместного ведения бюджета в одной таблице."
            "• *Интерактивные кнопки* для быстрого выбора действий."
            "• *Обработка ошибок и логирование* для стабильной и надёжной работы."
            "📊 **Настройка:**\n"
            "1. Создайте группу с помощью /create <ссылка-на-таблицу>\n"
            "2. Предоставьте в своей Google Таблице доступ редактора для бота\n"
            "3. Отправляйте голосовые сообщения для учета финансов!"
        )
        try:
            await update.message.reply_text(help_text, parse_mode='Markdown')
        except:
            await context.bot.send_message(context._chat_id, help_text, parse_mode='Markdown')
    
    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /info command"""
        user = update.effective_user
        chat = update.effective_chat
        
        info_text = (
            f"ℹ️ **Информация о боте**\n\n"
            f"👤 **Пользователь:** {user.first_name} {user.last_name or ''}\n"
            f"🆔 **ID пользователя:** {user.id}\n"
            f"📝 **Имя пользователя:** @{user.username or 'Не указано'}\n"
            f"💬 **ID чата:** {chat.id}\n"
            f"📅 **Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🤖 **Версия бота:** 1.0.0\n"
            f"📚 **Фреймворк:** python-telegram-bot"
        )
        await update.message.reply_text(info_text, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages: require group, then classify text."""
        user = update.effective_user
        message_text = update.message.text
        if not self._user_in_group(user.id):
            await self._prompt_group_required(update)
            return
        try:
            result = await self._classify_finance_text(message_text, user.id, user)
            if not result:
                result = {
                    "type": None,
                    "category": None,
                    "currency": None,
                    "amount": None,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "month": None,
                    "comment": None,
                    "source_text": message_text,
                    "username": user.username or f"user_{user.id}"
                }
            # Process transaction if classification was successful
            if result and result.get("type") and result.get("category"):
                try:
                    # Get user's group spreadsheet ID
                    group_id = self._user_group_id(user.id)
                    if group_id:
                        data = self._load_storage()
                        group = data.get("groups", {}).get(group_id, {})
                        spreadsheet_id = group.get("spreadsheet_id")
                        
                        if spreadsheet_id:
                            # Initialize transaction processor
                            config = Config()
                            sheets_manager = GoogleSheetsManager(config.service_account_file, spreadsheet_id)
                            processor = TransactionProcessor(sheets_manager)
                            
                            # Process the transaction
                            transaction_result = processor.process_transaction(result)
                            
                            if transaction_result["success"]:
                                result["transaction_status"] = "✅ Добавлено в таблицу"
                                # capture row id for later cancellation
                                result["row_id"] = transaction_result.get("row_id")
                                result["sheet_name"] = transaction_result.get("sheet_name")
                            else:
                                result["transaction_status"] = f"❌ {transaction_result.get('error', 'Не удалось добавить')}"
                        else:
                            result["transaction_status"] = "⚠️ Таблица не настроена"
                    else:
                        result["transaction_status"] = "⚠️ Пользователь не в группе"
                except Exception as e:
                    logger.error(f"Error processing transaction: {e}")
                    result["transaction_status"] = f"❌ Ошибка: {str(e)}"

            # Send result back to user with cancel button if transaction was successful
            # Format date as DD.MM.YYYY for display
            display_date = result.get('date')
            try:
                if display_date:
                    from datetime import datetime as _dt
                    display_date = _dt.strptime(display_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            except Exception:
                pass
            message_text = f"Статья: {result['category']},\nСумма: {result['amount']}\nВалюта: {result['currency']}\nКомментарий: {result['comment']}\nДата: {display_date}\nСтатус: {result['transaction_status']}"
            
            if result.get('transaction_status', '').startswith('✅') and result.get('row_id') and result.get('sheet_name'):
                # Include sheet name and unique row id in callback data
                callback_data = f"cancel|{result['sheet_name']}|{result['row_id']}"
                keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data=callback_data)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.message.reply_text(message_text, parse_mode='Markdown')
            
            logger.info(f"User {user.id} text classified: {message_text}")
        except Exception:
            logger.exception("Error classifying text message")
            await update.message.reply_text("❌ Ошибка обработки текста. Пожалуйста, попробуйте снова.")

    async def handle_audio_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming voice notes or audio files: download, transcribe, classify, and reply with JSON."""
        message = update.message
        user = update.effective_user
        if message is None:
            return
        if not self._user_in_group(user.id):
            await self._prompt_group_required(update)
            return
        try:
            # Determine file to download
            file_id = None
            if message.voice:
                file_id = message.voice.file_id
            elif message.audio:
                file_id = message.audio.file_id
            else:
                await message.reply_text("Пожалуйста, отправьте голосовое сообщение или аудиофайл.")
                return

            tg_file = await context.bot.get_file(file_id)

            # Save to a temporary file
            with tempfile.TemporaryDirectory() as tmpdir:
                ext = ".ogg" if message.voice else (Path(message.audio.file_name).suffix if message.audio and message.audio.file_name else ".mp3")
                local_path = Path(tmpdir) / f"audio{ext}"
                await tg_file.download_to_drive(custom_path=str(local_path))

                # Transcribe
                transcription_text = await self._transcribe_with_groq_whisper(str(local_path))
                if not transcription_text:
                    await message.reply_text("❌ Не удалось транскрибировать аудио.")
                    return

                # Classify
                result = await self._classify_finance_text(transcription_text, user.id, user)
                # Fallback if classification failed
                if not result:
                    result = {
                        "type": None,
                        "category": None,
                        "currency": None,
                        "amount": None,
                        "date": None,
                        "month": None,
                        "comment": None,
                        "source_text": transcription_text,
                        "username": user.username or f"user_{user.id}"
                    }

            # Process transaction if classification was successful
            if result and result.get("type") and result.get("category"):
                try:
                    # Get user's group spreadsheet ID
                    group_id = self._user_group_id(user.id)
                    if group_id:
                        data = self._load_storage()
                        group = data.get("groups", {}).get(group_id, {})
                        spreadsheet_id = group.get("spreadsheet_id")
                        
                        if spreadsheet_id:
                            # Initialize transaction processor
                            config = Config()
                            sheets_manager = GoogleSheetsManager(config.service_account_file, spreadsheet_id)
                            processor = TransactionProcessor(sheets_manager)
                            
                            # Process the transaction
                            transaction_result = processor.process_transaction(result)
                            
                            if transaction_result["success"]:
                                result["transaction_status"] = "✅ Добавлено в таблицу"
                                # capture row id for later cancellation
                                result["row_id"] = transaction_result.get("row_id")
                                result["sheet_name"] = transaction_result.get("sheet_name")
                            else:
                                result["transaction_status"] = f"❌ {transaction_result.get('error', 'Не удалось добавить')}"
                        else:
                            result["transaction_status"] = "⚠️ Таблица не настроена"
                    else:
                        result["transaction_status"] = "⚠️ Пользователь не в группе"
                except Exception as e:
                    logger.error(f"Error processing transaction: {e}")
                    result["transaction_status"] = f"❌ Ошибка: {str(e)}"
            else:
                result["transaction_status"] = "❌ Транзакция не классифицирована"

            print(result, type(result))
            
            display_date = result.get('date')
            try:
                if display_date:
                    from datetime import datetime as _dt
                    display_date = _dt.strptime(display_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            except Exception:
                pass

            # Send result back to user with cancel button if transaction was successful
            message_text = f"Статья: {result['category']},\nСумма: {result['amount']}\nВалюта: {result['currency']}\nКомментарий: {result['comment']}\nДата: {display_date}\nСтатус: {result['transaction_status']}"
            
            # Add cancel button if transaction was successfully added
            if result.get('transaction_status', '').startswith('✅') and result.get('row_id') and result.get('sheet_name'):
                # Include sheet name and unique row id in callback data
                callback_data = f"cancel|{result['sheet_name']}|{result['row_id']}"
                keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data=callback_data)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await message.reply_text(message_text, parse_mode='Markdown')
            
            logger.info(f"User {user.id} audio processed: {message_text}")
        except Exception as e:
            logger.exception("Error handling audio message")
            await message.reply_text("❌ Ошибка обработки аудио. Пожалуйста, попробуйте снова.")

    # -------------------- Group management --------------------
    def _ensure_storage(self) -> None:
        try:
            if not self.storage_path.exists():
                self.storage_path.write_text(json.dumps({}))
        except Exception as e:
            logger.error(f"Failed to ensure storage file: {e}")

    def _store_transaction_info(self, transaction_id: str, transaction_info: Dict[str, Any]) -> None:
        """Store transaction info for potential cancellation."""
        try:
            data = self._load_storage()
            if "pending_transactions" not in data:
                data["pending_transactions"] = {}
            data["pending_transactions"][transaction_id] = transaction_info
            self._save_storage(data)
        except Exception as e:
            logger.error(f"Failed to store transaction info: {e}")

    def _get_transaction_info(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get stored transaction info."""
        try:
            data = self._load_storage()
            return data.get("pending_transactions", {}).get(transaction_id)
        except Exception as e:
            logger.error(f"Failed to get transaction info: {e}")
            return None
    
    def _remove_transaction_info(self, transaction_id: str) -> None:
        """Remove stored transaction info."""
        try:
            data = self._load_storage()
            if "pending_transactions" in data and transaction_id in data["pending_transactions"]:
                del data["pending_transactions"][transaction_id]
                self._save_storage(data)
        except Exception as e:
            logger.error(f"Failed to remove transaction info: {e}")

    def _load_storage(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.storage_path.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            logger.exception("Failed to read storage; reinitializing")
        return {}

    def _save_storage(self, data: Dict[str, Any]) -> None:
        try:
            self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            logger.exception("Failed to save storage")

    def _is_admin(self, user_id: int) -> bool:
        return user_id in ADMIN_USER_IDS

    def _is_authorised(self, user_id: int) -> bool:
        try:
            data = self._load_storage()
            return user_id in set(data.get("authorised_users", {}).values())
        except Exception:
            return False

    def _is_admin_or_authorised(self, user_id: int) -> bool:
        return self._is_admin(user_id) or self._is_authorised(user_id)

    def _remove_user_from_group(self, user_id: int, group_id: str) -> bool:
        """Remove a user from a group."""
        try:
            data = self._load_storage()
            if group_id not in data.get("groups", {}):
                return False
            
            group = data["groups"][group_id]
            members = group.get("members", [])
            
            if user_id in members:
                members.remove(user_id)
                group["members"] = members
                data["groups"][group_id] = group
                self._save_storage(data)
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove user from group: {e}")
            return False

    def _delete_group(self, group_id: str) -> bool:
        """Delete an entire group."""
        try:
            data = self._load_storage()
            if group_id not in data.get("groups", {}):
                return False
            
            # Remove the group
            del data["groups"][group_id]
            self._save_storage(data)
            return True
        except Exception as e:
            logger.error(f"Failed to delete group: {e}")
            return False

    def _user_in_group(self, user_id: int) -> bool:
        data = self._load_storage()
        for group_id, group in data.get("groups", {}).items():
            members = group.get("members", [])
            if user_id in members:
                return True
        return False

    def _get_or_create_groups_root(self) -> Dict[str, Any]:
        data = self._load_storage()
        if "groups" not in data:
            data["groups"] = {}
        return data

    def _extract_spreadsheet_id(self, url: str) -> Optional[str]:
        """Extract spreadsheet ID from Google Sheets URL"""
        # Pattern for Google Sheets URLs
        patterns = [
            r'/spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'([a-zA-Z0-9-_]{44})'  # Google Sheets IDs are typically 44 characters
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _create_group(self, owner_id: int, title: Optional[str] = None, spreadsheet_id: Optional[str] = None) -> str:
        import secrets
        data = self._get_or_create_groups_root()
        group_id = secrets.token_hex(6)
        data["groups"][group_id] = {
            "title": title or f"Group-{group_id}",
            "owner_id": owner_id,
            "members": [owner_id],
            "invite_code": secrets.token_urlsafe(8),
            "spreadsheet_id": spreadsheet_id
        }
        self._save_storage(data)
        return group_id

    def _user_group_id(self, user_id: int) -> Optional[str]:
        data = self._load_storage()
        for gid, group in data.get("groups", {}).items():
            if user_id in group.get("members", []):
                return gid
        return None

    def _generate_invite_code(self, user_id: int) -> Optional[str]:
        import secrets
        data = self._load_storage()
        gid = self._user_group_id(user_id)
        if not gid:
            return None
        code = secrets.token_urlsafe(8)
        data["groups"][gid]["invite_code"] = code
        self._save_storage(data)
        return code

    def _join_with_code(self, user_id: int, code: str) -> bool:
        data = self._load_storage()
        for gid, group in data.get("groups", {}).items():
            if group.get("invite_code") == code:
                members = set(group.get("members", []))
                members.add(user_id)
                group["members"] = list(members)
                data["groups"][gid] = group
                self._save_storage(data)
                return True
        return False
    
    def _get_group_categories(self, user_id: int) -> Dict[str, Any]:
        """
        Get categories from the user's group spreadsheet by reading the data validation rule
        for the next cell in column C of the income and expense lists, and extracting the
        referenced range to fetch category names.
        """
        try:
            group_id = self._user_group_id(user_id)
            if not group_id:
                raise ValueError("Group ID not found")
            
            data = self._load_storage()
            group = data.get("groups", {}).get(group_id, {})
            spreadsheet_id = group.get("spreadsheet_id")
            
            if not spreadsheet_id:
                raise ValueError("Spreadsheet ID not found")
            
            config = Config()
            sheets_manager = GoogleSheetsManager(config.service_account_file, spreadsheet_id)

            def get_categories_from_validation(list_sheet: str, col: int) -> list:
                """
                Get categories from the data validation rule of the next empty cell in the given column.
                """
                try:
                    # Find the next empty row in the list sheet
                    next_row = sheets_manager.get_next_row(list_sheet)
                    # Google Sheets columns are 1-indexed, so col=3 for column C
                    cell = f"{list_sheet}!{chr(64+col)}{next_row}"
                    # Get data validation rule for the cell
                    validation = sheets_manager.get_data_validation(cell)
                    if not validation:
                        return []
                    # The validation formula is like "='Бюджет'!$A$4:$A$60"
                    formula = validation.get("condition", {}).get("values", [{}])[0].get("userEnteredValue", "")
                    if not formula:
                        # Try to get from "formula1" or "formula" if present
                        formula = validation.get("condition", {}).get("formula1", "") or validation.get("condition", {}).get("formula", "")
                    if not formula:
                        # Try to get from "showCustomUi" or "inputMessage" if present
                        formula = validation.get("showCustomUi", "") or validation.get("inputMessage", "")
                    # Try to extract the range from the formula
                    # Accepts ='Sheet'!$A$4:$A$60 or =Sheet!A4:A60
                    m = re.search(r"=+'?([^'!]+)'?!\$?([A-Z])\$?(\d+):\$?([A-Z])\$?(\d+)", formula)
                    if not m:
                        m = re.search(r"=([A-Za-z0-9_]+)!([A-Z])(\d+):([A-Z])(\d+)", formula)
                    if not m:
                        return []
                    sheet_name = m.group(1)
                    col_start = m.group(2)
                    row_start = int(m.group(3))
                    col_end = m.group(4)
                    row_end = int(m.group(5))
                    # Read the range from the referenced sheet
                    range_str = f"{col_start}{row_start}:{col_end}{row_end}"
                    values = sheets_manager.read_data(sheet_name, range_str)
                    # Flatten and filter out empty values
                    categories = [v for row in values for v in row if v and str(v).strip()]
                    return categories
                except Exception as e:
                    logger.error(f"Error extracting categories from data validation: {e}")
                    return []

            categories = {"income": [], "expense": []}
            # For income
            try:
                categories["income"] = get_categories_from_validation(
                    config.income_sheet_name, 3  # column C
                )
            except Exception as e:
                logger.error(f"Error getting income categories: {e}")
            # For expense
            try:
                categories["expense"] = get_categories_from_validation(
                    config.expense_sheet_name, 3  # column C
                )
            except Exception as e:
                logger.error(f"Error getting expense categories: {e}")

            # Fallback to config if empty
            if not categories["income"]:
                categories["income"] = config.income_categories
            if not categories["expense"]:
                categories["expense"] = config.expense_categories

            return categories
                
        except Exception as e:
            logger.error(f"Error getting group categories: {e}")
            config = Config()
            return {
                "income": config.income_categories,
                "expense": config.expense_categories
            }

    async def _prompt_group_required(self, update: Update) -> None:
        keyboard = [
            [InlineKeyboardButton("🆕 Создать группу", callback_data="create_group")],
            [InlineKeyboardButton("🔗 Присоединиться по коду", callback_data="join_group_prompt")]
        ]
        await update.message.reply_text(
            "Вы еще не в группе. Создайте группу или присоединитесь по коду.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def create_group_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not self._is_admin_or_authorised(user.id):
            await update.message.reply_text("❌ Вы не авторизованы для создания групп. Попросите админа дать код /auth.")
            return
        if self._user_in_group(user.id):
            await update.message.reply_text("Вы уже состоите в группе.")
            return
        
        # Check if user provided a spreadsheet link
        if context.args:
            spreadsheet_link = context.args[0]
            spreadsheet_id = self._extract_spreadsheet_id(spreadsheet_link)
            
            if not spreadsheet_id:
                await update.message.reply_text("❌ Неверная ссылка на Google Sheets. Пожалуйста, предоставьте действительную ссылку.")
                return
            
            # Create group with spreadsheet ID
            gid = self._create_group(user.id, spreadsheet_id=spreadsheet_id)
            
            # Ask user to add service account as editor
            await update.message.reply_text(
                f"✅ Группа создана с ID: {gid}\n\n"
                f"📊 ID таблицы: {spreadsheet_id}\n\n"
                f"🔐 **Важно:** Пожалуйста, добавьте этот сервисный аккаунт как редактора в вашу таблицу:\n"
                f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
                f"1. Откройте вашу Google Таблицу\n"
                f"2. Нажмите кнопку 'Поделиться'\n"
                f"3. Добавьте указанный выше email как редактора\n"
                f"4. Используйте /invite для получения кода приглашения для других"
            )
        else:
            await update.message.reply_text(
                "📊 Для создания группы, пожалуйста, предоставьте ссылку на Google Sheets:\n\n"
                "Использование: /create <ссылка_на_таблицу>\n\n"
                "Пример: /create https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit"
            )

    async def invite_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        code = self._generate_invite_code(user.id)
        if not code:
            await update.message.reply_text("❌ Вы должны быть в группе, чтобы создать приглашение.")
            return
        await update.message.reply_text(
            f"🔗 Поделитесь этим кодом для приглашения других: {code}\nОни могут присоединиться с помощью /join {code}"
        )

    async def join_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not self._is_admin_or_authorised(user.id):
            await update.message.reply_text("❌ Вы не авторизованы для присоединения к группам. Попросите админа дать код /auth.")
            return
        if self._user_in_group(user.id):
            await update.message.reply_text("Вы уже состоите в группе.")
            return
        if not context.args:
            await update.message.reply_text("Использование: /join <код_приглашения>")
            return
        code = context.args[0]
        ok = self._join_with_code(user.id, code)
        if ok:
            await update.message.reply_text("✅ Успешно присоединились к группе.")
        else:
            await update.message.reply_text("❌ Неверный код приглашения.")

    async def auth_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/auth for admins to generate codes; /auth <code> for users to authorize."""
        user = update.effective_user
        args = context.args if hasattr(context, 'args') else []
        data = self._load_storage()
        # Ensure roots
        if "auth_codes" not in data:
            data["auth_codes"] = []
        if "authorised_users" not in data:
            data["authorised_users"] = {}
        # Claiming a code
        if args:
            code = args[0]
            if code in data["auth_codes"]:
                data["authorised_users"][code] = user.id
                # Single-use: remove code after claim
                data["auth_codes"] = [c for c in data["auth_codes"] if c != code]
                self._save_storage(data)
                await update.message.reply_text("✅ Теперь вы авторизованы.")
                return
            # Already used by same user
            if code in data["authorised_users"] and data["authorised_users"][code] == user.id:
                await update.message.reply_text("ℹ️ Вы уже авторизованы с этим кодом.")
                return
            await update.message.reply_text("❌ Неверный или уже использованный код.")
            return
        # Generate a code (admins only)
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ Только админы могут создавать коды авторизации.")
            return
        import secrets
        new_code = secrets.token_urlsafe(8)
        data["auth_codes"].append(new_code)
        self._save_storage(data)
        await update.message.reply_text(f"🔐 Код авторизации: {new_code}\nПоделитесь с пользователем для выполнения /auth {new_code}")

    async def leave_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /leave command - remove user from group or delete group if creator."""
        user = update.effective_user
        group_id = self._user_group_id(user.id)
        
        if not group_id:
            await update.message.reply_text("❌ Вы не состоите ни в одной группе.")
            return
        
        data = self._load_storage()
        group = data.get("groups", {}).get(group_id, {})
        
        if not group:
            await update.message.reply_text("❌ Группа не найдена.")
            return
        
        # Check if user is the group creator
        if group.get("owner_id") == user.id:
            # Delete the entire group
            success = self._delete_group(group_id)
            if success:
                await update.message.reply_text("✅ Группа успешно удалена (вы были создателем).")
            else:
                await update.message.reply_text("❌ Не удалось удалить группу.")
        else:
            # Just remove user from group
            success = self._remove_user_from_group(user.id, group_id)
            if success:
                await update.message.reply_text("✅ Вы покинули группу.")
            else:
                await update.message.reply_text("❌ Не удалось покинуть группу.")

    async def _transcribe_with_groq_whisper(self, file_path: str) -> Optional[str]:
        """Transcribe an audio file using Groq Whisper."""
        if not groq_client.api_key:
            logger.error("GROQ_API_KEY is not set")
            return None
        try:
            with open(file_path, "rb") as f:
                transcript = groq_client.audio.transcriptions.create(
                    file=(Path(file_path).name, f.read()),
                    model="whisper-large-v3"
                )
            # SDK returns an object; extract text
            text = getattr(transcript, 'text', None) or (transcript.get('text') if isinstance(transcript, dict) else None)
            return text
        except Exception as e:
            logger.error(f"Groq Whisper transcription failed: {e}")
            return None

    async def _classify_finance_text(self, transcription_text: str, user_id: int, user = None, retry = True) -> Optional[Dict[str, Any]]:
        """Classify transcription into finance JSON using Groq Llama-8B."""
        if not groq_client.api_key:
            logger.error("GROQ_API_KEY is not set")
            return None
        try:
            # Get categories from user's group spreadsheet
            group_categories = self._get_group_categories(user_id)
            all_categories = []
            for cat_list in group_categories.values():
                all_categories.extend(cat_list)
            
            print(all_categories, group_categories)
            # Get month names from config
            config = Config()
            month_names = config.month_names
            
            system_prompt = FINANCE_JSON_INSTRUCTIONS
            categories_str = str(group_categories) #", ".join(all_categories)
            months_str = ", ".join(month_names)
            user_prompt = (
                f"The current date is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n\n"
                f"Categories list: [{categories_str}]\n\n"
                f"Month names list: [{months_str}]\n\n"
                f"Transcription: {transcription_text}\n\n"
                "Respond with ONLY JSON."
            )

            completion = groq_client.chat.completions.create(
                model="meta-llama/llama-4-maverick-17b-128e-instruct", #"llama-3.1-8b-instant",
                temperature=0.1,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            content = completion.choices[0].message.content if completion and completion.choices else ""
            print(content)
            # With response_format json_object, content should be raw JSON
            content = content.strip()
            try:
                data = json.loads(content)
            except Exception as e:
                print(e)
                # Try to find JSON within the text
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start:end+1])
                else:
                    data = None
            print(data)
            # Validate keys minimally
            if isinstance(data, dict):
                data.setdefault("type", None)
                data.setdefault("category", None)
                data.setdefault("currency", None)
                data.setdefault("amount", None)
                # Default to today's date if model omitted date
                if not data.get("date"):
                    data["date"] = datetime.now().strftime("%Y-%m-%d")
                # Default to current month if model omitted month
                if not data.get("month"):
                    current_month = datetime.now().month - 1  # 0-indexed
                    data["month"] = month_names[current_month]
                data.setdefault("comment", None)
                data.setdefault("source_text", transcription_text)
                # Add username if user object is provided
                if user:
                    data.setdefault("username", user.username or f"user_{user.id}")
            return data
        except Exception as e:
            if retry:
                return self._classify_finance_text(transcription_text, user_id, user, retry=False)
            else:
                logger.error(f"Groq Llama classification failed: {e}")
                return None
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        await query.answer()  # Answer the callback query
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "info":
            await self.info_command(update, context)
        elif query.data == "time":
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await query.edit_message_text(f"🕒 Текущее время: {current_time}")
        elif query.data == "create_group":
            user = update.effective_user
            if not self._is_admin_or_authorised(user.id):
                await query.edit_message_text("❌ Не авторизован. Попросите админа дать код /auth.")
            elif self._user_in_group(user.id):
                await query.edit_message_text("Вы уже состоите в группе.")
            else:
                await query.edit_message_text(
                    "📊 Для создания группы, пожалуйста, предоставьте ссылку на Google Sheets:\n\n"
                    "Использование: /create <ссылка_на_таблицу>\n\n"
                    "Пример: /create https://docs.google.com/spreadsheets/d/your-spreadsheet-id/edit"
                )
        elif query.data == "join_group_prompt":
            user = update.effective_user
            if not self._is_admin_or_authorised(user.id):
                await query.edit_message_text("❌ Не авторизован. Попросите админа дать код /auth.")
            else:
                await query.edit_message_text("Отправьте /join <код_приглашения> для присоединения к группе.")
        elif query.data.startswith("cancel|"):
            # Handle cancel transaction by row id in column L
            try:
                parts = query.data.split('|', 2)
                if len(parts) != 3:
                    await query.edit_message_text("❌ Неверные данные для отмены.")
                    return
                _, sheet_name, row_id = parts
                user = update.effective_user
                group_id = self._user_group_id(user.id)
                if not group_id:
                    await query.edit_message_text("❌ Группа не найдена.")
                    return
                group_data = self._load_storage()["groups"][group_id]
                spreadsheet_id = group_data.get("spreadsheet_id")
                if not spreadsheet_id:
                    await query.edit_message_text("❌ Для этой группы не настроена таблица.")
                    return
                config = Config()
                sheets_manager = GoogleSheetsManager(config.service_account_file, spreadsheet_id)
                success = sheets_manager.delete_row_by_id(sheet_name, row_id)
                if success:
                    await query.edit_message_text("✅ Транзакция отменена и удалена из таблицы.")
                else:
                    await query.edit_message_text("❌ Не удалось найти транзакцию для отмены.")
            except Exception as e:
                logger.error(f"Error canceling transaction: {e}")
                await query.edit_message_text("❌ Ошибка при отмене транзакции.")
        
        logger.info(f"Callback query from user {query.from_user.id}: {query.data}")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Send error message to user if possible
        if update and hasattr(update, 'effective_chat'):
            error_message = "❌ Извините, что-то пошло не так. Пожалуйста, попробуйте позже."
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=error_message
                )
            except Exception as e:
                logger.error(f"Could not send error message: {e}")

def main():
    """Main function to run the bot"""
    # Environment variables are already validated at module level
    
    # Create and run the bot
    bot = TelegramBot()
    
    print("🤖 Starting Telegram Bot...")
    print("📱 Bot is running. Press Ctrl+C to stop.")
    
    try:
        # Start the bot
        bot.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")

if __name__ == '__main__':
    main()
