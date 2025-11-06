import os
from typing import List, Optional, Dict, Any
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleSheetsManager:
    """Manages Google Sheets operations for the financial accounting application."""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, service_account_file: str, spreadsheet_id: str):
        """
        Initialize the Google Sheets manager.
        
        Args:
            service_account_file: Path to the service account JSON file
            spreadsheet_id: ID of the Google Sheets spreadsheet
        """
        self.service_account_file = service_account_file
        self.spreadsheet_id = spreadsheet_id
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API using service account."""
        try:
            if not os.path.exists(self.service_account_file):
                raise FileNotFoundError(
                    f"Service account file '{self.service_account_file}' not found. "
                    "Please download it from Google Cloud Console."
                )
            
            # Create credentials from service account file
            creds = Credentials.from_service_account_file(
                self.service_account_file, 
                scopes=self.SCOPES
            )
            
            self.service = build('sheets', 'v4', credentials=creds)
            
        except Exception as error:
            raise Exception(f"Failed to authenticate with service account: {error}")
    
    def create_sheet(self, sheet_name: str, headers: List[str]) -> bool:
        """
        Create a new sheet with headers if it doesn't exist.
        
        Args:
            sheet_name: Name of the sheet to create
            headers: List of column headers
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if sheet exists
            if self.sheet_exists(sheet_name):
                return True
            
            # Create new sheet
            request = {
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }
            
            body = {'requests': [request]}
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            
            # Add headers to the new sheet
            self.write_data(sheet_name, [headers], 'A1')
            return True
            
        except HttpError as error:
            print(f"Error creating sheet '{sheet_name}': {error}")
            return False
    
    def sheet_exists(self, sheet_name: str) -> bool:
        """
        Check if a sheet exists in the spreadsheet.
        
        Args:
            sheet_name: Name of the sheet to check
            
        Returns:
            bool: True if sheet exists, False otherwise
        """
        try:
            result = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheets = result.get('sheets', [])
            return any(sheet['properties']['title'] == sheet_name for sheet in sheets)
            
        except HttpError as error:
            print(f"Error checking if sheet exists: {error}")
            return False
    
    def read_data(self, sheet_name: str, range_name: str = None) -> List[List]:
        """
        Read data from a sheet.
        
        Args:
            sheet_name: Name of the sheet to read from
            range_name: Range to read (e.g., 'A1:F100'), if None reads entire sheet
            
        Returns:
            List[List]: Data from the sheet
        """
        try:
            if range_name is None:
                range_name = f"{sheet_name}!A:F"
            else:
                range_name = f"{sheet_name}!{range_name}"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            return result.get('values', [])
            
        except HttpError as error:
            print(f"Error reading data from sheet '{sheet_name}': {error}")
            return []
    
    def write_data(self, sheet_name: str, data: List[List], start_cell: str = 'A1') -> bool:
        """
        Write data to a sheet.
        
        Args:
            sheet_name: Name of the sheet to write to
            data: Data to write (list of lists)
            start_cell: Starting cell (e.g., 'A1')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            range_name = f"{sheet_name}!{start_cell}"
            
            body = {
                'values': data
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            return True
            
        except HttpError as error:
            print(f"Error writing data to sheet '{sheet_name}': {error}")
            return False
    
    def append_data(self, sheet_name: str, data: List[List], date: str, username:str, id_value: Optional[str] = None) -> bool:
        """
        Instead of appending, set values of cells in the row get_last_row(sheet_name), columns A:F to input data values.
        
        Args:
            sheet_name: Name of the sheet to write to
            data: Data to write (list of lists)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Determine the last row (1-based)
            last_row = self.get_next_row(sheet_name)
            # Prepare the range for columns A:F in the last row
            start_cell = f"B{last_row}"
            end_cell = f"F{last_row}"
            range_name = f"{sheet_name}!{start_cell}:{end_cell}"
            body = {
                'values': data
            }
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            date_range = f"{sheet_name}!A{last_row}"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=date_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[date]]}
            ).execute()
            # If id_value provided, write it to column L of the same row
            if id_value is not None:
                id_range = f"{sheet_name}!L{last_row}"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=id_range,
                    valueInputOption='RAW',
                    body={'values': [[id_value]]}
                ).execute()
            if username is not None:
                user_range = f"{sheet_name}!M{last_row}"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=user_range,
                    valueInputOption='RAW',
                    body={'values': [[username]]}
                ).execute()
            return True
        except HttpError as error:
            print(f"Error writing data to sheet '{sheet_name}': {error}")
            return False

    def get_next_row(self, sheet_name: str) -> int:
        """
        Get the first row with an empty cell in column A.
        
        Args:
            sheet_name: Name of the sheet
            
        Returns:
            int: Row number of the first empty cell in column A (1-based)
        """
        try:
            data = self.read_data(sheet_name)
            for idx, row in enumerate(data, start=1):
                # Check if column A (first cell) is empty or missing
                if len(row) == 0 or row[4] == "" or row[4] is None:
                    return idx
            # If no empty cell found, return next row after last
            return len(data) + 1
        except Exception:
            return 2

    def delete_row_by_id(self, sheet_name: str, id_value: str) -> bool:
        """
        Find the row where column L equals id_value and delete that row.
        """
        try:
            # Read column L
            range_name = f"{sheet_name}!L:L"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])
            # Find matching row (values is 1-based with header possibly not present)
            target_row = None
            for idx, row in enumerate(values, start=1):
                cell = row[0] if row else ''
                if str(cell).strip() == str(id_value).strip():
                    target_row = idx
                    break
            if target_row is None:
                return False
            # Need sheetId
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            sheet_id = None
            for s in spreadsheet.get('sheets', []):
                if s.get('properties', {}).get('title') == sheet_name:
                    sheet_id = s.get('properties', {}).get('sheetId')
                    break
            if sheet_id is None:
                return False
            # Delete the row (target_row is 1-based)
            request_body = {
                'requests': [
                    {
                        'deleteDimension': {
                            'range': {
                                'sheetId': sheet_id,
                                'dimension': 'ROWS',
                                'startIndex': target_row - 1,
                                'endIndex': target_row
                            }
                        }
                    }
                ]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request_body
            ).execute()
            return True
        except Exception as e:
            print(f"Error deleting row by id in sheet '{sheet_name}': {e}")
            return False

    def clear_last_transaction(self, sheet_name: str, row_number: int) -> bool:
        """
        Remove the last transaction row.
        
        Args:
            sheet_name: Name of the sheet to remove from
            row_number: Row number to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if row_number <= 1:  # No data to remove (only headers)
                return False
            
            # Get the sheet ID
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            sheet_id = None
            for s in spreadsheet.get("sheets", []):
                if s.get("properties", {}).get("title") == sheet_name:
                    sheet_id = s.get("properties", {}).get("sheetId")
                    break
            
            if sheet_id is None:
                return False
            
            # Delete the row
            request_body = {
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_number - 1,  # Convert to 0-based index
                                "endIndex": row_number
                            }
                        }
                    }
                ]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=request_body
            ).execute()
            
            return True
            
        except HttpError as error:
            print(f"Error clearing last transaction from sheet '{sheet_name}': {error}")
            return False

    def get_data_validation(self, cell: str) -> dict:
        """
        Get the data validation rule of a specific cell.

        Args:
            cell: The A1 notation of the cell (e.g., 'Sheet1!C5')

        Returns:
            dict: The data validation rule if present, else empty dict
        """
        try:
            # Parse the sheet name and cell from the A1 notation
            if "!" in cell:
                sheet_name, cell_ref = cell.split("!")
            else:
                sheet_name, cell_ref = cell, cell

            # Get the sheet ID
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            sheet_id = None
            for s in spreadsheet.get("sheets", []):
                if s.get("properties", {}).get("title") == sheet_name:
                    sheet_id = s.get("properties", {}).get("sheetId")
                    break
            if sheet_id is None:
                return {}

            # Convert A1 cell_ref to gridRange
            import re
            m = re.match(r"([A-Z]+)(\d+)", cell_ref)
            if not m:
                return {}
            col_letters, row_str = m.groups()
            row = int(row_str) - 1  # zero-based
            # Convert column letters to zero-based index
            col = 0
            for c in col_letters:
                col = col * 26 + (ord(c.upper()) - ord('A') + 1)
            col -= 1

            # Get the sheet with data validations
            result = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                ranges=[cell],
                fields="sheets.data.rowData.values.dataValidation,sheets.properties"
            ).execute()
            #print(result)
            sheets = result.get("sheets", [])
            if not sheets:
                return {}
            data = sheets[0].get("data", [])
            if not data:
                return {}
            row_data = data[0].get("rowData", [])
            #if row >= len(row_data):
            #    return {}
            cell_data = row_data[0].get("values", [])
            #if col >= len(cell_data):
            #    return {}
            validation = cell_data[0].get("dataValidation", {})
            print(validation)
            return validation if validation else {}
        except Exception as e:
            print(f"Error getting data validation for cell '{cell}': {e}")
            return {}
