import csv
import json
import logging
import datetime as dt
import re # Import re for cleaning description
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Dict, Any, Optional

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [PARSER] %(message)s')
BASE_DIR = Path(__file__).parent
VENDORS_FILE_PATH = BASE_DIR / 'vendors.json'
USER_RULES_FILE = BASE_DIR / 'user_rules.json'

# --- Helper Function for Cleaning ---
# This function is now used both for rule matching and creating the cleaned description
def _clean_description_for_rule(description: str) -> str:
    """
    Cleans a transaction description.
    Removes common date patterns (MM/DD, MM/DD/YY(YY)) from the end and trims whitespace.
    """
    if not description:
        return ""
    # Remove date patterns from the end
    cleaned = re.sub(r'\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*$', '', description)
    # Additional cleaning: Remove potential multiple spaces within the string
    cleaned = re.sub(r'\s{2,}', ' ', cleaned) # Replace 2+ spaces with single space
    return cleaned.strip()

# --- Data Structures ---
class Transaction:
    """Represents a single financial transaction."""
    def __init__(self,
                 date: dt.date,
                 description: str, # This will now hold the CLEANED description
                 amount: Decimal,
                 category: str = "Uncategorized",
                 transaction_type: Optional[str] = None,
                 source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None,
                 raw_description: Optional[str] = None, # Holds the ORIGINAL description
                 id: Optional[int] = None):
        # Type checking
        if not isinstance(date, dt.date):
            if isinstance(date, dt.datetime): date = date.date()
            else: raise TypeError(f"Transaction date must be date/datetime, got {type(date)}")
        if not isinstance(amount, Decimal):
             raise TypeError(f"Transaction amount must be Decimal, got {type(amount)}")

        self.id = id
        self.date = date
        # Assign cleaned description to the main 'description' attribute
        self.description = description # Assumes cleaned version is passed in
        self.amount = amount
        self.category = category
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type
        self.source_filename = source_filename
        # Assign original description to 'raw_description'
        self.raw_description = raw_description if raw_description else description # Fallback if raw wasn't provided

    def to_dict(self) -> Dict[str, Any]:
        """Converts the transaction to a dictionary, capitalizing the category."""
        display_category = self.category.title() if self.category else "Uncategorized"
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "description": self.description, # Return the cleaned description
            "amount": str(self.amount),
            "category": display_category,
            "transaction_type": self.transaction_type,
            "source_account_type": self.source_account_type,
            "source_filename": self.source_filename,
            "raw_description": self.raw_description, # Also include raw description
        }

    def __repr__(self):
        """Provides a developer-friendly representation."""
        # Show cleaned description in repr for brevity
        return (f"Transaction(id={self.id}, date={self.date}, desc='{self.description[:30]}...', "
                f"amount={self.amount:.2f}, category='{self.category}')")

# --- Rule Loading ---
# (load_rules_from_json remains the same)
def load_rules_from_json(file_path: Path, keys_lowercase: bool = True) -> Dict[str, str]:
    """Loads rules from a JSON file, optionally lowercasing keys."""
    rules_data = {}
    if not file_path.is_file():
        logging.warning(f"Rules file not found at {file_path}. Returning empty ruleset.")
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            if keys_lowercase:
                rules_data = {key.lower(): value for key, value in raw_data.items()}
            else:
                rules_data = raw_data
            logging.info(f"Successfully loaded {len(rules_data)} rules from {file_path}.")
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from rules file: {file_path}. Returning empty ruleset.")
    except Exception as e:
        logging.error(f"Error loading rules file {file_path}: {e}", exc_info=True)
    return rules_data

VENDORS_DATA = load_rules_from_json(VENDORS_FILE_PATH, keys_lowercase=True)
USER_RULES_DATA = load_rules_from_json(USER_RULES_FILE, keys_lowercase=True)


# --- Categorization Logic ---
# (categorize_transaction remains the same - it uses raw_description for matching)
def categorize_transaction(transaction: Transaction,
                           user_rules: Dict[str, str],
                           vendor_rules: Dict[str, str]) -> None:
    """Categorizes a transaction, prioritizing user rules over vendor rules."""
    desc_to_check = transaction.raw_description # Use raw for matching
    if not desc_to_check:
        transaction.category = "Uncategorized"; return

    # Check User Rules First (using cleaned description for key lookup)
    cleaned_desc_lower = _clean_description_for_rule(desc_to_check).lower()
    if cleaned_desc_lower in user_rules:
        transaction.category = user_rules[cleaned_desc_lower]
        logging.debug(f"Categorized '{desc_to_check}' as '{transaction.category}' using USER RULE for key '{cleaned_desc_lower}'")
        return

    # Check Vendor Rules Second (using raw description for keyword lookup)
    desc_lower = desc_to_check.lower()
    for keyword, display_category in vendor_rules.items():
        if keyword in desc_lower:
            transaction.category = display_category
            logging.debug(f"Categorized '{desc_to_check}' as '{transaction.category}' using VENDOR RULE for keyword '{keyword}'")
            return

    logging.debug(f"Could not categorize '{desc_to_check}'. Left as '{transaction.category}'.")


# --- CSV Parsing Functions ---
def parse_checking_csv(file_path: Path) -> List[Transaction]:
    """Parses a Chase Checking Activity CSV file."""
    transactions: List[Transaction] = []
    filename = file_path.name
    logging.info(f"Starting parsing for checking file: {filename}")
    try:
        if not file_path.is_file(): logging.error(f"Checking file not found: {file_path}"); return []
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try: header = next(reader)
            except StopIteration: logging.error(f"File {filename} is empty."); return []
            if not header or not all(h in header for h in ["Posting Date", "Description", "Amount"]): logging.warning(f"File {filename} might have unexpected headers.")
            try:
                idx_date, idx_desc, idx_amount = header.index("Posting Date"), header.index("Description"), header.index("Amount")
                idx_type = header.index("Type") if "Type" in header else -1
            except ValueError as e: logging.error(f"Missing critical header in {filename}: {e}."); return []

            row_num = 1
            for row in reader:
                row_num += 1
                if not row or len(row) <= max(idx_date, idx_desc, idx_amount): continue
                try:
                    post_date = dt.datetime.strptime(row[idx_date], '%m/%d/%Y').date()
                    raw_desc_from_csv = row[idx_desc] # Get the original description
                    amount = Decimal(row[idx_amount])
                    trans_type = row[idx_type] if idx_type != -1 and len(row) > idx_type else None

                    # --- Change: Clean description here ---
                    cleaned_desc = _clean_description_for_rule(raw_desc_from_csv)

                    transaction = Transaction(
                        date=post_date,
                        description=cleaned_desc, # Assign cleaned version
                        amount=amount,
                        transaction_type=trans_type,
                        source_account_type='checking',
                        source_filename=filename,
                        raw_description=raw_desc_from_csv # Assign original version
                    )
                    categorize_transaction(transaction, USER_RULES_DATA, VENDORS_DATA)
                    transactions.append(transaction)
                except (ValueError, TypeError, InvalidOperation) as e: logging.warning(f"Skipping checking row {row_num} due to conversion error: {e} | Row: {row}")
                except Exception as e: logging.error(f"Unexpected error processing checking row {row_num}: {e} | Row: {row}")
    except Exception as e: logging.error(f"Failed to process checking file {filename}: {e}", exc_info=True)
    logging.info(f"Finished parsing {filename}. Found {len(transactions)} transactions.")
    return transactions

def parse_credit_csv(file_path: Path) -> List[Transaction]:
    """Parses a Chase Credit Card Activity CSV file."""
    transactions: List[Transaction] = []
    filename = file_path.name
    logging.info(f"Starting parsing for credit card file: {filename}")
    try:
        if not file_path.is_file(): logging.error(f"Credit card file not found: {file_path}"); return []
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try: header = next(reader)
            except StopIteration: logging.error(f"File {filename} is empty."); return []
            if not header or not all(h in header for h in ["Post Date", "Description", "Amount", "Type"]): logging.warning(f"File {filename} might have unexpected headers.")
            try:
                idx_post_date, idx_desc, idx_amount, idx_type = header.index("Post Date"), header.index("Description"), header.index("Amount"), header.index("Type")
                idx_category_bank = header.index("Category") if "Category" in header else -1
            except ValueError as e: logging.error(f"Missing critical header in {filename}: {e}."); return []

            row_num = 1
            for row in reader:
                row_num += 1
                if not row or len(row) <= max(idx_post_date, idx_desc, idx_amount, idx_type): continue
                try:
                    post_date = dt.datetime.strptime(row[idx_post_date], '%m/%d/%Y').date()
                    raw_desc_from_csv = row[idx_desc] # Get the original description
                    amount = Decimal(row[idx_amount])
                    trans_type = row[idx_type]
                    bank_category = row[idx_category_bank] if idx_category_bank != -1 and len(row) > idx_category_bank else None

                    # --- Change: Clean description here ---
                    cleaned_desc = _clean_description_for_rule(raw_desc_from_csv)

                    transaction = Transaction(
                        date=post_date,
                        description=cleaned_desc, # Assign cleaned version
                        amount=amount,
                        transaction_type=trans_type,
                        source_account_type='credit',
                        source_filename=filename,
                        raw_description=raw_desc_from_csv # Assign original version
                    )
                    categorize_transaction(transaction, USER_RULES_DATA, VENDORS_DATA)
                    transactions.append(transaction)
                except (ValueError, TypeError, InvalidOperation) as e: logging.warning(f"Skipping credit row {row_num} due to conversion error: {e} | Row: {row}")
                except Exception as e: logging.error(f"Unexpected error processing credit row {row_num}: {e} | Row: {row}")
    except Exception as e: logging.error(f"Failed to process credit file {filename}: {e}", exc_info=True)
    logging.info(f"Finished parsing {filename}. Found {len(transactions)} transactions.")
    return transactions


# --- Main Execution Example (for testing) ---
if __name__ == '__main__':
    script_dir = Path(__file__).parent
    data_dir = script_dir / 'data'
    if not data_dir.is_dir(): print(f"Error: Data directory not found at {data_dir}")
    else:
        checking_file = data_dir / 'Chase3112_Activity_checking.csv'
        credit_file = data_dir / 'Chase9883_Activity_credit.csv'
        print("-" * 20); print(f"Attempting to parse Checking CSV: {checking_file}")
        checking_transactions = parse_checking_csv(checking_file)
        if checking_transactions:
            print(f"Parsed {len(checking_transactions)} checking transactions.")
            print("Example (first 5):")
            for tx in checking_transactions[:5]:
                 print(f"  Cleaned: '{tx.description}' | Raw: '{tx.raw_description}' | Cat: {tx.category}")
        else: print("No transactions parsed from checking file.")

        print("-" * 20); print(f"Attempting to parse Credit CSV: {credit_file}")
        credit_transactions = parse_credit_csv(credit_file)
        if credit_transactions:
            print(f"Parsed {len(credit_transactions)} credit transactions.")
            print("Example (first 5):")
            for tx in credit_transactions[:5]:
                 print(f"  Cleaned: '{tx.description}' | Raw: '{tx.raw_description}' | Cat: {tx.category}")
        else: print("No transactions parsed from credit file.")

        print("-" * 20)
        all_transactions = checking_transactions + credit_transactions
        print(f"Total transactions parsed: {len(all_transactions)}")
        if all_transactions:
            print("\nCategory Counts (Initial Parse):")
            category_counts = {}
            for tx in all_transactions: cat = tx.category if tx.category else "Uncategorized"; category_counts[cat] = category_counts.get(cat, 0) + 1
            sorted_categories = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
            for category, count in sorted_categories: print(f"- {category}: {count}")
            print("\nExample to_dict() output (first transaction):"); print(all_transactions[0].to_dict())

