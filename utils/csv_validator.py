import csv
import io
from typing import List, Dict, Tuple
import chardet
from utils.url_validator import URLValidator
import logging

logger = logging.getLogger(__name__)

class CSVValidator:
    def __init__(self, max_file_size: int = 5 * 1024 * 1024):  # 5MB default
        self.max_file_size = max_file_size
        self.url_validator = URLValidator()
        self.required_fields = ['url', 'name']
        self.optional_fields = ['description', 'check_frequency']

    def validate_file_size(self, file_content: bytes) -> bool:
        """Check if file size is within limits"""
        return len(file_content) <= self.max_file_size

    def detect_encoding(self, file_content: bytes) -> str:
        """Detect file encoding"""
        result = chardet.detect(file_content)
        return result['encoding'] or 'utf-8'

    def validate_csv_format(self, content: str) -> Tuple[bool, str, List[Dict]]:
        """
        Validate CSV format and content
        Returns: (is_valid, error_message, parsed_data)
        """
        try:
            reader = csv.DictReader(io.StringIO(content))
            
            # Validate headers
            if not reader.fieldnames:
                return False, "CSV file has no headers", []
            
            # Check required fields
            missing_fields = [f for f in self.required_fields if f not in reader.fieldnames]
            if missing_fields:
                return False, f"Missing required columns: {', '.join(missing_fields)}", []
            
            # Validate and process rows
            valid_rows = []
            errors = []
            
            for row_num, row in enumerate(reader, start=2):
                # Validate required fields are not empty
                if any(not row.get(field, '').strip() for field in self.required_fields):
                    errors.append(f"Row {row_num}: Empty required field(s)")
                    continue
                
                # Validate and normalize URL
                try:
                    url = self.url_validator.normalize_url(row['url'].strip())
                    if not self.url_validator.is_valid_url(url):
                        errors.append(f"Row {row_num}: Invalid URL format")
                        continue
                except Exception as e:
                    errors.append(f"Row {row_num}: URL validation error - {str(e)}")
                    continue
                
                # Validate name length
                if len(row['name'].strip()) > 100:  # Adjust max length as needed
                    errors.append(f"Row {row_num}: Name too long (max 100 characters)")
                    continue
                
                # Validate check frequency if provided
                if 'check_frequency' in row and row['check_frequency'].strip():
                    try:
                        freq = int(row['check_frequency'])
                        if not (1 <= freq <= 1440):  # 1 minute to 24 hours
                            errors.append(f"Row {row_num}: Check frequency must be between 1 and 1440 minutes")
                            continue
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid check frequency")
                        continue
                
                # Add validated row
                valid_row = {
                    'url': url,
                    'name': row['name'].strip(),
                    'description': row.get('description', '').strip(),
                    'check_frequency': int(row.get('check_frequency', 60))
                }
                valid_rows.append(valid_row)
            
            # Return results
            if errors:
                error_message = "\n".join(errors)
                return False, error_message, valid_rows
            
            return True, "", valid_rows
            
        except csv.Error as e:
            return False, f"CSV parsing error: {str(e)}", []
        except Exception as e:
            logger.error(f"CSV validation error: {str(e)}")
            return False, "Invalid CSV format", []

    async def process_csv_file(self, file_content: bytes) -> Tuple[bool, str, List[Dict]]:
        """
        Process and validate a CSV file
        Returns: (success, error_message, valid_rows)
        """
        # Check file size
        if not self.validate_file_size(file_content):
            return False, f"File size exceeds maximum limit of {self.max_file_size/1024/1024}MB", []
        
        # Detect and decode file content
        try:
            encoding = self.detect_encoding(file_content)
            content = file_content.decode(encoding)
        except UnicodeDecodeError:
            return False, "Unable to decode file content. Please ensure it's a valid CSV file.", []
        
        # Validate CSV format and content
        return self.validate_csv_format(content)