# Environment Setup

This application now uses environment variables for all sensitive configuration. Follow these steps to set up your environment:

## 1. Create .env file

Create a `.env` file in the project root directory with the following variables:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Admin User IDs (comma-separated)
ADMIN_USER_IDS=your_admin_user_ids_here

# Groq API Configuration
GROQ_API_KEY=your_groq_api_key_here

# Google Sheets Service Account
SERVICE_ACCOUNT_EMAIL=your_service_account_email_here
SERVICE_ACCOUNT_FILE=service_account.json

# Storage Configuration
FINANCE_BOT_STORAGE=groups.json

# Sheet Names
INCOME_SHEET_NAME=Доходы факт
EXPENSE_SHEET_NAME=Расходы факт
```

## 2. Required Environment Variables

### Required (will cause startup failure if missing):
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather
- `GROQ_API_KEY`: Your Groq API key
- `SERVICE_ACCOUNT_EMAIL`: Your Google service account email

### Optional (have defaults):
- `ADMIN_USER_IDS`: Comma-separated list of admin user IDs
- `SERVICE_ACCOUNT_FILE`: Path to service account JSON file (default: service_account.json)
- `FINANCE_BOT_STORAGE`: Path to groups storage file (default: groups.json)
- `INCOME_SHEET_NAME`: Name of income sheet (default: Доходы факт)
- `EXPENSE_SHEET_NAME`: Name of expense sheet (default: Расходы факт)

## 3. Security Notes

- Never commit your `.env` file to version control
- The `.env` file is already in `.gitignore`
- Use `env.example` as a template for your `.env` file
- Keep your service account JSON file secure and never commit it

## 4. Getting Required Values

### Telegram Bot Token:
1. Message @BotFather on Telegram
2. Create a new bot with `/newbot`
3. Copy the token provided

### Groq API Key:
1. Visit https://console.groq.com/
2. Sign up/login and get your API key

### Google Service Account:
1. Go to Google Cloud Console
2. Create a service account
3. Download the JSON key file
4. Save it as `service_account.json` in your project directory
5. The email address is in the JSON file under `client_email`

## 5. Running the Application

After setting up your `.env` file:

```bash
pip install -r requirements.txt
python main.py
```

The application will validate all required environment variables on startup.
