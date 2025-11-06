from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from google_sheets_manager import GoogleSheetsManager
from config import Config

class TransactionProcessor:
    """Processes financial transactions and manages them in Google Sheets."""
    
    def __init__(self, sheets_manager: GoogleSheetsManager):
        """
        Initialize the transaction processor.
        
        Args:
            sheets_manager: Google Sheets manager instance
        """
        self.sheets_manager = sheets_manager
        self.config = Config()
        self._initialize_sheets()
    
    def _initialize_sheets(self):
        """Initialize the income and expense sheets with headers if they don't exist."""
        try:
            # Create income sheet if it doesn't exist
            self.sheets_manager.create_sheet(
                self.config.income_sheet_name,
                self.config.column_headers
            )
            
            # Create expense sheet if it doesn't exist
            self.sheets_manager.create_sheet(
                self.config.expense_sheet_name,
                self.config.column_headers
            )
            
        except Exception as e:
            print(f"Error initializing sheets: {e}")
    
    def process_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a transaction and add it to the appropriate sheet.
        
        Args:
            transaction_data: Dictionary containing transaction information
            
        Returns:
            Dict containing success status and additional information
        """
        try:
            # Validate transaction data
            validation_result = self._validate_transaction(transaction_data)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"]
                }
            
            # Extract transaction type and determine target sheet
            transaction_type = transaction_data["type"].lower()
            sheet_name = self.config.get_sheet_name(transaction_type)
            
            # Prepare row data (excluding the 'type' field)
            # Convert date to DD.MM.YYYY for spreadsheet storage
            try:
                dt = datetime.strptime(transaction_data["date"], "%Y-%m-%d")
                date_cell = dt.strftime("%d.%m.%Y")
            except Exception:
                date_cell = transaction_data["date"]
            print(date_cell)
            row_data = [
                transaction_data["month"],
                transaction_data["category"],
                transaction_data["comment"],
                transaction_data["amount"],
                transaction_data["currency"]
            ]
            
            # Generate a full timestamp ID for the row and add to column L
            row_id = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            # Add the transaction to the appropriate sheet
            success = self.sheets_manager.append_data(sheet_name, [row_data], date=date_cell, username=transaction_data.get("username", "Unknown"), id_value=row_id)
            
            if success:
                return {
                    "success": True,
                    "sheet_name": sheet_name,
                    "row_id": row_id,
                    "message": f"Transaction added to {sheet_name} sheet"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to add transaction to {sheet_name} sheet"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Error processing transaction: {str(e)}"
            }
    
    def _validate_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate transaction data.
        
        Args:
            transaction_data: Dictionary containing transaction information
            
        Returns:
            Dict containing validation status and error message if any
        """
        required_fields = ["type", "date", "month", "category", "comment", "amount", "currency"]
        
        # Check if all required fields are present
        for field in required_fields:
            if field not in transaction_data:
                return {
                    "valid": False,
                    "error": f"Missing required field: {field}"
                }
        
        # Validate transaction type
        transaction_type = transaction_data["type"].lower()
        if transaction_type not in ["income", "expense"]:
            return {
                "valid": False,
                "error": f"Invalid transaction type: {transaction_type}. Must be 'income' or 'expense'"
            }
        
        # Validate date format
        try:
            datetime.strptime(transaction_data["date"], "%Y-%m-%d")
        except ValueError:
            return {
                "valid": False,
                "error": "Invalid date format. Use YYYY-MM-DD"
            }
        
        # Validate month format
        '''try:
            month = int(transaction_data["month"])
            if month.type() != str:
                raise ValueError("Month must be a string")
            if month not in self.config.month_names:
                raise ValueError(f"Invalid month: {month}. Valid months: {', '.join(self.config.month_names)}")
        except ValueError:
            return {
                "valid": False,
                "error": f"Invalid month: {month}. Valid months: {', '.join(self.config.month_names)}"
            }'''
        
        # Validate category
        '''valid_categories = self.config.get_categories(transaction_type)
        if transaction_data["category"] not in valid_categories:
            return {
                "valid": False,
                "error": f"Invalid category '{transaction_data['category']}' for {transaction_type}. Valid categories: {', '.join(valid_categories)}"
            }'''
        
        # Validate amount
        try:
            amount = float(transaction_data["amount"])
            if amount <= 0:
                return {
                    "valid": False,
                    "error": "Amount must be greater than 0"
                }
        except ValueError:
            return {
                "valid": False,
                "error": "Invalid amount. Must be a valid number"
            }
        
        # Validate currency
        if not transaction_data["currency"] or len(transaction_data["currency"]) != 3:
            return {
                "valid": False,
                "error": "Invalid currency. Must be a 3-letter currency code (e.g., USD, EUR)"
            }
        
        return {"valid": True}
    
    def get_transactions(self, transaction_type: str) -> List[List]:
        """
        Get all transactions of a specific type.
        
        Args:
            transaction_type: Type of transactions to retrieve ('income' or 'expense')
            
        Returns:
            List of transaction rows (excluding headers)
        """
        try:
            sheet_name = self.config.get_sheet_name(transaction_type)
            data = self.sheets_manager.read_data(sheet_name)
            
            # Return data excluding headers
            if len(data) > 1:
                return data[1:]  # Skip header row
            else:
                return []
                
        except Exception as e:
            print(f"Error retrieving {transaction_type} transactions: {e}")
            return []
    
    def get_transaction_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all transactions.
        
        Returns:
            Dict containing summary information
        """
        try:
            income_data = self.get_transactions("income")
            expense_data = self.get_transactions("expense")
            
            # Calculate totals
            total_income = sum(float(row[4]) for row in income_data if len(row) > 4 and row[4])
            total_expenses = sum(float(row[4]) for row in expense_data if len(row) > 4 and row[4])
            net_amount = total_income - total_expenses
            
            return {
                "total_income": total_income,
                "total_expenses": total_expenses,
                "net_amount": net_amount,
                "income_count": len(income_data),
                "expense_count": len(expense_data)
            }
            
        except Exception as e:
            print(f"Error calculating transaction summary: {e}")
            return {
                "total_income": 0,
                "total_expenses": 0,
                "net_amount": 0,
                "income_count": 0,
                "expense_count": 0
            }
    
    def search_transactions(self, query: str, transaction_type: str = None) -> List[List]:
        """
        Search transactions by query.
        
        Args:
            query: Search query
            transaction_type: Optional filter by transaction type
            
        Returns:
            List of matching transaction rows
        """
        try:
            results = []
            
            if transaction_type is None or transaction_type.lower() == "income":
                income_data = self.get_transactions("income")
                for row in income_data:
                    if any(query.lower() in str(field).lower() for field in row):
                        results.append(["Income"] + row)
            
            if transaction_type is None or transaction_type.lower() == "expense":
                expense_data = self.get_transactions("expense")
                for row in expense_data:
                    if any(query.lower() in str(field).lower() for field in row):
                        results.append(["Expense"] + row)
            
            return results
            
        except Exception as e:
            print(f"Error searching transactions: {e}")
            return []
