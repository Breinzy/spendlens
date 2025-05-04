# parser.py

import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from typing import List, Dict, Optional, Tuple, Any # <--- Added Any import

# --- Local Import ---
# Import database functions needed for rules
import database

# Configure logging
log = logging.getLogger('parser') # Use specific logger name
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)


# --- Constants ---
VENDOR_RULES_FILE = 'vendors.json'
# --- REMOVED JSON FILE CONSTANTS ---
# USER_RULES_FILE = 'user_rules.json'
# LLM_RULES_FILE = 'llm_rules.json'

# --- Transaction Class Definition ---
# (Ensure this matches the definition in database.py)
# Define here for standalone testing if needed, but prefer importing
try:
    from database import Transaction
except ImportError:
    log.warning("Could not import Transaction from database in parser. Defining placeholder.")
    class Transaction:
        def __init__(self, id: int = 0, user_id: int = 0, date: Optional[dt.date] = None, description: Optional[str] = None,
                     amount: Optional[Decimal] = None, category: Optional[str] = None,
                     transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                     source_filename: Optional[str] = None, raw_description: Optional[str] = None):
            self.id = id
            self.user_id = user_id
            self.date = date
            self.description = description
            self.amount = amount
            self.category = category
            self.transaction_type = transaction_type
            self.source_account_type = source_account_type
            self.source_filename = source_filename
            self.raw_description = raw_description if raw_description else description

        def to_dict(self) -> Dict[str, Any]:
            return {
                "id": self.id, "user_id": self.user_id,
                "date": self.date.isoformat() if self.date else None,
                "description": self.description,
                "amount": str(self.amount) if self.amount is not None else None,
                "category": self.category, "transaction_type": self.transaction_type,
                "source_account_type": self.source_account_type,
                "source_filename": self.source_filename,
                "raw_description": self.raw_description
            }

# --- Rule Loading Functions ---

def load_vendor_rules(filepath: str) -> Dict[str, str]:
    """Loads GLOBAL vendor categorization rules from a JSON file."""
    rules = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    log.warning(f"Vendor rules file {filepath} is empty.")
                    return {}
                rules = json.loads(content)
            log.info(f"Successfully loaded {len(rules)} vendor rules from {filepath}.")
        except json.JSONDecodeError:
            log.error(f"Error decoding JSON from {filepath}. File might be corrupt or invalid JSON.")
            return {}
        except Exception as e:
            log.error(f"Error loading vendor rules from {filepath}: {e}", exc_info=True)
            return {}
    else:
        log.warning(f"Vendor rules file not found: {filepath}. No vendor rules loaded.")
    # Ensure keys are lowercase for case-insensitive matching
    return {k.lower(): v for k, v in rules.items()}

# --- Load VENDOR rules once ---
VENDOR_RULES = load_vendor_rules(VENDOR_RULES_FILE)

# --- REMOVED Global USER_RULES and LLM_RULES dictionaries and loading functions ---

# --- UPDATED Rule Saving Functions (Use Database) ---

def add_user_rule(user_id: int, description_fragment: str, category: str):
    """Adds or updates a user-specific rule IN THE DATABASE."""
    if not description_fragment or not category:
        log.warning(f"Attempted to add user rule for user {user_id} with empty description or category.")
        return

    rule_key = description_fragment.lower().strip()
    try:
        database.save_user_rule(user_id, rule_key, category)
        # No need to update in-memory dict, it will be fetched next time
    except Exception as e:
        # Database function should log errors, but we can log here too
        log.error(f"Failed to save user rule to database for user {user_id}: {e}", exc_info=True)


def save_llm_rule(user_id: int, description_fragment: str, category: str):
    """Adds or updates an LLM-inferred rule IN THE DATABASE."""
    if not description_fragment or not category:
        log.warning(f"Attempted to add LLM rule for user {user_id} with empty description or category.")
        return

    rule_key = description_fragment.lower().strip()
    try:
        database.save_llm_rule(user_id, rule_key, category)
         # No need to update in-memory dict
    except Exception as e:
        log.error(f"Failed to save LLM rule to database for user {user_id}: {e}", exc_info=True)

# --- REMOVED clear_user_rules function (no longer needed for JSON) ---


# --- Categorization Logic (User-Aware) ---
# --- UPDATED HIERARCHY & DATABASE FETCH ---
def categorize_transaction(user_id: int, description: str) -> str:
    """
    Categorizes a transaction based on description using the hierarchy:
    1. User Rules (from DB)
    2. Vendor Rules (from global VENDOR_RULES)
    3. LLM Inferred Rules (from DB)
    """
    if not description:
        return 'Uncategorized'

    desc_lower = description.lower()

    # --- Fetch user-specific rules from DB ---
    user_rules = database.get_user_rules(user_id)
    llm_rules = database.get_llm_rules(user_id)
    # --- End Fetch ---

    # 1. Check User Rules First (Highest Priority)
    sorted_user_keys = sorted(user_rules.keys(), key=len, reverse=True)
    for key in sorted_user_keys:
        if key in desc_lower:
            category = user_rules[key]
            log.debug(f"User {user_id}: Matched user rule '{key}' for description '{description}'. Category: {category}")
            return category

    # 2. Check Vendor Rules (Middle Priority)
    # VENDOR_RULES is already loaded globally
    sorted_vendor_keys = sorted(VENDOR_RULES.keys(), key=len, reverse=True)
    for key in sorted_vendor_keys:
        if key in desc_lower:
            category = VENDOR_RULES[key]
            log.debug(f"User {user_id}: Matched vendor rule '{key}' for description '{description}'. Category: {category}")
            return category

    # 3. Check LLM Inferred Rules (Lowest Priority)
    sorted_llm_keys = sorted(llm_rules.keys(), key=len, reverse=True)
    for key in sorted_llm_keys:
        if key in desc_lower:
            category = llm_rules[key]
            log.debug(f"User {user_id}: Matched LLM rule '{key}' for description '{description}'. Category: {category}")
            return category
    # --- END HIERARCHY UPDATE ---

    # 4. Default if no match
    log.debug(f"User {user_id}: No rule matched for description '{description}'. Defaulting to Uncategorized.")
    return 'Uncategorized'


# --- CSV Parsing Functions (User-Aware) ---

# --- UPDATED SIGNATURE ---
def parse_chase_csv_common(user_id: int, filepath: str, account_type: str) -> List[Transaction]:
    """Common logic for parsing Chase CSV files for a specific user."""
    transactions = []
    filename = os.path.basename(filepath)
    log.info(f"User {user_id}: Starting parsing for {account_type} file: {filename}")
    try:
        # --- REMOVED rule loading calls here ---
        # Rules are now fetched per transaction inside categorize_transaction

        with open(filepath, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            # Check for empty file or missing headers
            if not reader.fieldnames:
                 log.error(f"User {user_id}: CSV file {filename} is empty or has no header row.")
                 raise ValueError(f"Empty or headerless CSV file: {filename}")

            fieldnames_lower = [name.lower().strip() for name in reader.fieldnames]

            date_cols = ['transaction date', 'posting date']
            desc_cols = ['description']
            amount_cols = ['amount']

            date_col = next((name for name in reader.fieldnames if name.lower().strip() in date_cols), None)
            desc_col = next((name for name in reader.fieldnames if name.lower().strip() in desc_cols), None)
            amount_col = next((name for name in reader.fieldnames if name.lower().strip() in amount_cols), None)
            type_col = next((name for name in reader.fieldnames if name.lower().strip() == 'type'), None)

            if not all([date_col, desc_col, amount_col]):
                 missing = []
                 if not date_col: missing.append("Date ('Transaction Date' or 'Posting Date')")
                 if not desc_col: missing.append("Description")
                 if not amount_col: missing.append("Amount")
                 log.error(f"User {user_id}: CSV file {filename} is missing required columns: {', '.join(missing)}. Cannot parse.")
                 raise ValueError(f"Missing required columns in {filename}: {', '.join(missing)}")

            for i, row in enumerate(reader):
                try:
                    date_str = row.get(date_col)
                    raw_desc = row.get(desc_col, '').strip()
                    amount_str = row.get(amount_col, '0').strip()

                    if not date_str or not raw_desc:
                        log.warning(f"User {user_id}: Skipping row {i+1} in {filename} due to missing date or description.")
                        continue

                    description = ' '.join(raw_desc.split())

                    try:
                        transaction_date = dt.datetime.strptime(date_str, '%m/%d/%Y').date()
                    except ValueError:
                        log.warning(f"User {user_id}: Skipping row {i+1} in {filename} due to invalid date format: {date_str}")
                        continue

                    try:
                        amount = Decimal(amount_str)
                    except InvalidOperation:
                        log.warning(f"User {user_id}: Skipping row {i+1} in {filename} due to invalid amount: {amount_str}")
                        continue

                    transaction_type_detail = row.get(type_col) if type_col else None
                    if transaction_type_detail:
                        tx_type = transaction_type_detail.strip()
                    elif amount > 0:
                        tx_type = 'PAYMENT_RECEIVED' if 'payment' in description.lower() else 'DEPOSIT' if 'deposit' in description.lower() else 'CREDIT'
                    else:
                        tx_type = 'WITHDRAWAL' if 'withdraw' in description.lower() else 'DEBIT'

                    # --- Pass user_id to categorization ---
                    category = categorize_transaction(user_id, description)
                    # --- End Pass ---

                    transactions.append(Transaction(
                        id=0,
                        user_id=user_id, # Pass user_id to Transaction object
                        date=transaction_date,
                        description=description,
                        amount=amount,
                        category=category,
                        transaction_type=tx_type,
                        source_account_type=account_type,
                        source_filename=filename,
                        raw_description=raw_desc
                    ))
                except Exception as row_error:
                    log.error(f"User {user_id}: Error processing row {i+1} in {filename}: {row_error}", exc_info=True)

        log.info(f"User {user_id}: Finished parsing {filename}. Found {len(transactions)} transactions.")
        return transactions

    except FileNotFoundError:
        log.error(f"User {user_id}: File not found: {filepath}")
        return []
    except ValueError as ve:
        log.error(f"User {user_id}: Parsing error for {filename}: {ve}")
        return []
    except Exception as e:
        log.error(f"User {user_id}: Failed to parse {filepath}: {e}", exc_info=True)
        return []

# --- UPDATED SIGNATURES ---
def parse_checking_csv(user_id: int, filepath: str) -> List[Transaction]:
    """Parses a Chase checking account CSV file for a specific user."""
    return parse_chase_csv_common(user_id, filepath, 'checking')

def parse_credit_csv(user_id: int, filepath: str) -> List[Transaction]:
    """Parses a Chase credit card CSV file for a specific user."""
    return parse_chase_csv_common(user_id, filepath, 'credit')
# --- END UPDATES ---


# --- Example Usage (for testing parser.py directly) ---
if __name__ == '__main__':
    log.info("parser.py executed directly for testing.")

    # --- Requires database setup for testing now ---
    log.warning("Direct execution of parser.py for testing now requires database interaction.")
    log.warning("Ensure database is initialized and potentially create a test user.")

    # Example: Assume a test user exists with ID 1
    test_user_id = 1
    # You might need to create this user first if running standalone
    # database.create_user("parser_test", "test_password_hash") # Hashing done elsewhere

    # Create dummy data directory if it doesn't exist
    if not os.path.exists('data'):
        os.makedirs('data')

    # --- Create Dummy CSV Files for Testing ---
    dummy_checking_path = 'data/dummy_checking.csv'
    checking_data = [
        ['Transaction Date', 'Posting Date', 'Description', 'Amount', 'Type'],
        ['03/15/2025', '03/15/2025', 'PAYROLL DEPOSIT - TEST CORP', '2000.00', 'ACH_CREDIT'],
        ['03/10/2025', '03/11/2025', 'VENDOR RULE MART', '-75.50', 'DEBIT_CARD'],
        ['03/05/2025', '03/05/2025', 'USER RULE PLACE', '-50.00', 'DEBIT_CARD'],
        ['03/02/2025', '03/02/2025', 'LLM RULE CAFE', '-10.00', 'DEBIT_CARD'],
        ['03/01/2025', '03/01/2025', 'SOMETHING UNKNOWN', '-25.00', 'DEBIT_CARD'],
    ]
    try:
        with open(dummy_checking_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(checking_data)
        log.info("Created dummy checking CSV for testing.")
    except IOError as e:
        log.error(f"Failed to create dummy checking CSV: {e}")

    # --- Setup Dummy Rules in DB for Testing ---
    try:
        log.info(f"Setting up dummy rules for test user {test_user_id}")
        # Clear existing rules for test user first
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_rules WHERE user_id = ?", (test_user_id,))
        cursor.execute("DELETE FROM llm_rules WHERE user_id = ?", (test_user_id,))
        conn.commit()
        database.close_db_connection(conn, "clear_test_rules")

        # Add test rules
        database.save_user_rule(test_user_id, "user rule place", "User Category")
        database.save_llm_rule(test_user_id, "llm rule cafe", "LLM Category")
        # Assume "vendor rule mart" exists in vendors.json -> "Vendor Category"
        if "vendor rule mart" not in VENDOR_RULES:
             log.warning("Test assumes 'vendor rule mart' exists in vendors.json")

    except Exception as db_err:
        log.error(f"Failed to set up dummy rules in DB for testing: {db_err}")


    # --- Test Parsing ---
    print("\n--- Testing Checking Parser (User Aware) ---")
    checking_tx = parse_checking_csv(test_user_id, dummy_checking_path)
    for tx in checking_tx:
        print(tx.to_dict())
        # Expected categories: Income, Vendor Category, User Category, LLM Category, Uncategorized

    # --- Test Rule Addition (DB) ---
    print("\n--- Testing Rule Addition (DB) ---")
    add_user_rule(test_user_id, "something unknown", "New User Category")
    print("Checking DB for new rule...")
    rules = database.get_user_rules(test_user_id)
    print("Current User Rules from DB:", rules)


    # Clean up dummy file
    # try:
    #     if os.path.exists(dummy_checking_path): os.remove(dummy_checking_path)
    #     log.info("Cleaned up dummy checking CSV.")
    # except OSError as e:
    #     log.error(f"Error cleaning up dummy file: {e}")

