import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for the financial accounting application."""
    
    def __init__(self):
        # Google Sheets API service account file
        self.service_account_file = os.getenv('SERVICE_ACCOUNT_FILE', 'service_account.json')
        
        # Sheet names for income and expenses
        self.income_sheet_name = os.getenv('INCOME_SHEET_NAME', 'Доходы факт')
        self.expense_sheet_name = os.getenv('EXPENSE_SHEET_NAME', 'Расходы факт')

        self.income_categories = [
            "Зарплата",
            "Премия",
            "Бонус",
            "Другое"
        ]
        self.expense_categories = [
            "Продукты",
            "Одежда",
            "Другое"
        ]
        
        # Column headers for the sheets
        self.column_headers = [
            "Date",
            "Month", 
            "Category",
            "Comment",
            "Amount",
            "Currency"
        ]
        

        self.month_names = [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь"
        ]

    def get_sheet_name(self, transaction_type: str) -> str:
        """Get sheet name based on transaction type."""
        if transaction_type.lower() == "income":
            return self.income_sheet_name
        elif transaction_type.lower() == "expense":
            return self.expense_sheet_name
        else:
            raise ValueError(f"Invalid transaction type: {transaction_type}")
