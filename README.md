# Finance Organizer Telegram Bot

A comprehensive Telegram bot for financial transaction management using voice/audio transcription, AI classification, and Google Sheets integration.

## Features

- 🎤 **Voice/Audio Transcription**: Uses Whisper via Groq API for accurate transcription
- 🤖 **AI Classification**: Automatically classifies financial transactions using Llama model
- 📊 **Google Sheets Integration**: Stores transactions in organized spreadsheets
- 👥 **Group Management**: Create and manage groups for collaborative finance tracking
- 💰 **Transaction Processing**: Automatic categorization and storage of income/expenses
- 🌍 **Multi-language Support**: Handles transactions in various languages
- 📱 **Interactive Interface**: User-friendly commands and inline keyboards

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

**Option 1: Using .env file (Recommended)**
1. Copy `env.example` to `.env`
2. Fill in your actual values in the `.env` file
3. The application will automatically load these variables

**Option 2: Set environment variables directly**
```bash
# Telegram Bot Token (from @BotFather)
export TELEGRAM_BOT_TOKEN="your_bot_token_here"

# Groq API Key (for Whisper transcription and Llama classification)
export GROQ_API_KEY="your_groq_api_key_here"

# Service Account Email (for Google Sheets access)
export SERVICE_ACCOUNT_EMAIL="your-service-account@your-project.iam.gserviceaccount.com"
```

**See SETUP.md for detailed environment configuration instructions.**

### 3. Google Sheets Setup

1. **Create a Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google Sheets API

2. **Create Service Account**:
   - Go to "IAM & Admin" > "Service Accounts"
   - Create a new service account
   - Download the JSON credentials file
   - Rename it to `service_account.json` and place it in the project root

3. **Create Google Sheets Spreadsheet**:
   - Create a new Google Sheets document
   - Create a "config" sheet with the following structure:
     ```
     Type        | Category
     income      | Salary
     income      | Freelance
     income      | Investment
     expense     | Food
     expense     | Transportation
     expense     | Utilities
     ```

### 4. Run the Bot

```bash
python main.py
```

## Usage

### Basic Commands

- `/start` - Start the bot and show welcome message
- `/help` - Show help information and available commands
- `/info` - Display user and bot information

### Group Management

- `/create <spreadsheet_link>` - Create a new group with Google Sheets integration
- `/invite` - Get invite code for your group
- `/join <code>` - Join a group with invite code

### Voice Commands

1. **Send a voice message** or audio file to the bot
2. The bot will automatically:
   - Transcribe the audio using Whisper
   - Classify the content as income/expense
   - Extract relevant details (amount, category, date, etc.)
   - Add the transaction to your Google Sheets
   - Send back a detailed JSON response

### Example Voice Messages

- "I spent $25 on lunch today"
- "Received $500 salary payment"
- "Paid $120 for electricity bill yesterday"
- "Got $50 gift from mom"

## How It Works

### 1. Audio Processing
- Bot receives voice/audio message
- Downloads and saves to temporary file
- Uses Groq API with Whisper model for transcription

### 2. AI Classification
- Transcribed text is sent to Llama model via Groq
- Model extracts structured financial data:
  - Transaction type (income/expense)
  - Category (from your spreadsheet config)
  - Amount and currency
  - Date (with relative date resolution)
  - Month (from config.py month names)
  - Comments

### 3. Data Storage
- Transaction data is processed by TransactionProcessor
- Added to appropriate Google Sheets (income/expense sheets)
- User receives confirmation with transaction status

## Project Structure

```
finance organizer/
├── main.py                    # Main bot file with all handlers
├── config.py                  # Configuration class with categories and month names
├── google_sheets_manager.py   # Google Sheets API operations
├── transaction_processor.py   # Transaction processing and validation
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

## Configuration

### Categories
Categories are dynamically loaded from your Google Sheets "config" sheet. The bot will automatically use the categories you define there.

### Month Names
Month names are defined in `config.py` and support multiple languages. The bot automatically assigns the correct month based on the transaction date.

### Spreadsheet Structure
The bot expects the following sheets:
- **config**: Contains category definitions
- **Доходы факт** (Income): Stores income transactions
- **Расходы факт** (Expenses): Stores expense transactions

## Troubleshooting

### Common Issues

1. **"GROQ_API_KEY is not set"**
   - Make sure you've set the GROQ_API_KEY environment variable
   - Verify your Groq API key is valid

2. **"Service account not authorized"**
   - Ensure the service account email is added as an editor to your spreadsheet
   - Check that service_account.json is in the project root

3. **"Categories not found"**
   - Verify your "config" sheet exists in the spreadsheet
   - Check the sheet structure matches the expected format

4. **"Bot not responding to voice"**
   - Ensure you're in a group (use /create or /join)
   - Check that the group has a valid spreadsheet ID

### Logging

The bot includes comprehensive logging. Check the console output for:
- User interactions
- API responses
- Error messages
- Transaction processing status

## Security Notes

- Never commit your API keys or credentials to version control
- Use environment variables for sensitive data
- The service account should only have access to the specific spreadsheet
- Consider implementing user authentication for sensitive operations

## API Limits

- **Groq API**: Check your Groq account for rate limits
- **Google Sheets API**: 100 requests per 100 seconds per user
- **Telegram Bot API**: 30 messages per second

## License

This project is open source and available under the MIT License.
