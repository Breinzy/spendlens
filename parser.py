# parser.py

import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from typing import List, Dict, Optional, Tuple, Any # <--- Added Any import

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
USER_RULES_FILE = 'user_rules.json'
# --- ADDED LLM RULES FILE ---
LLM_RULES_FILE = 'llm_rules.json'
# --- END ADDITION ---

# --- Transaction Class Definition ---
# (Ensure this matches the definition in database.py)
class Transaction:
    def __init__(self, id: int, date: dt.date, description: str, amount: Decimal,
                 category: str, transaction_type: Optional[str] = None,
                 source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None,
                 raw_description: Optional[str] = None):
        self.id = id # Note: ID will be 0 initially, DB assigns final ID
        self.date = date
        self.description = description
        self.amount = amount
        self.category = category
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type
        self.source_filename = source_filename
        self.raw_description = raw_description if raw_description else description # Fallback

    # --- CORRECTED TYPE HINT ---
    def to_dict(self) -> Dict[str, Any]:
    # --- END CORRECTION ---
        """Converts the Transaction object to a dictionary."""
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "description": self.description,
            "amount": str(self.amount) if self.amount is not None else None, # Keep as string for JSON
            "category": self.category,
            "transaction_type": self.transaction_type,
            "source_account_type": self.source_account_type,
            "source_filename": self.source_filename,
            "raw_description": self.raw_description
        }

# --- Rule Loading Functions ---

def load_rules(filepath: str) -> Dict[str, str]:
    """Loads categorization rules from a JSON file."""
    rules = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Handle empty file case
                content = f.read()
                if not content:
                    log.warning(f"Rules file {filepath} is empty.")
                    return {}
                rules = json.loads(content)
            log.info(f"Successfully loaded {len(rules)} rules from {filepath}.")
        except json.JSONDecodeError:
            log.error(f"Error decoding JSON from {filepath}. File might be corrupt or invalid JSON.")
            return {} # Return empty dict on error
        except Exception as e:
            log.error(f"Error loading rules from {filepath}: {e}", exc_info=True)
            return {} # Return empty dict on error
    else:
        log.warning(f"Rules file not found: {filepath}. No rules loaded.")
    # Ensure keys are lowercase for case-insensitive matching
    return {k.lower(): v for k, v in rules.items()}

# Load rules once when the module is imported
VENDOR_RULES = load_rules(VENDOR_RULES_FILE)
USER_RULES = load_rules(USER_RULES_FILE)
# --- Load LLM rules ---
LLM_RULES = load_rules(LLM_RULES_FILE)
# --- End Load ---

def load_user_rules() -> Dict[str, str]:
    """Loads user-specific rules, ensuring keys are lowercase."""
    global USER_RULES # Modify the global variable
    USER_RULES = load_rules(USER_RULES_FILE)
    return USER_RULES

# --- ADDED: Function to load LLM rules ---
def load_llm_rules() -> Dict[str, str]:
    """Loads LLM-inferred rules, ensuring keys are lowercase."""
    global LLM_RULES # Modify the global variable
    LLM_RULES = load_rules(LLM_RULES_FILE)
    return LLM_RULES
# --- END ADDITION ---

def add_user_rule(description_fragment: str, category: str):
    """Adds or updates a user-specific rule and saves it to the file."""
    global USER_RULES
    if not description_fragment or not category:
        log.warning("Attempted to add user rule with empty description or category.")
        return

    # Use a simplified, lowercase version of the description fragment as the key
    # For simplicity now, using the lowercase fragment directly
    rule_key = description_fragment.lower().strip()

    # Add/update the rule in memory
    USER_RULES[rule_key] = category
    log.info(f"Added/Updated user rule: '{rule_key}' -> '{category}'")

    # Save the updated rules back to the file
    try:
        # Sort keys for consistent file output (optional)
        sorted_rules = dict(sorted(USER_RULES.items()))
        with open(USER_RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted_rules, f, indent=4, ensure_ascii=False)
        log.info(f"Successfully saved updated user rules to {USER_RULES_FILE}.")
    except IOError as e:
        log.error(f"Error saving user rules to {USER_RULES_FILE}: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Unexpected error saving user rules: {e}", exc_info=True)

# --- ADDED: Function to save LLM rules ---
# Note: This saves rules one by one. For performance, batch saving might be better.
def save_llm_rule(description_fragment: str, category: str):
    """Adds or updates an LLM-inferred rule and saves it to the file."""
    global LLM_RULES
    if not description_fragment or not category:
        log.warning("Attempted to add LLM rule with empty description or category.")
        return

    rule_key = description_fragment.lower().strip()

    # Add/update the rule in memory
    LLM_RULES[rule_key] = category
    log.info(f"Added/Updated LLM rule: '{rule_key}' -> '{category}'")

    # Save the updated rules back to the file
    try:
        # Sort keys for consistent file output (optional)
        sorted_rules = dict(sorted(LLM_RULES.items()))
        with open(LLM_RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted_rules, f, indent=4, ensure_ascii=False)
        log.info(f"Successfully saved updated LLM rules to {LLM_RULES_FILE}.")
    except IOError as e:
        log.error(f"Error saving LLM rules to {LLM_RULES_FILE}: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Unexpected error saving LLM rules: {e}", exc_info=True)
# --- END ADDITION ---


# --- MODIFIED FUNCTION ---
def clear_user_rules():
    """Clears user-specific rules from memory ONLY. Does NOT delete the file."""
    global USER_RULES
    log.warning(f"Clearing user rules from memory (file {USER_RULES_FILE} will NOT be deleted).")
    USER_RULES = {} # Clear in-memory rules
    # The file user_rules.json is intentionally left untouched.
    # It will be reloaded the next time load_user_rules() or load_rules(USER_RULES_FILE) is called,
    # or if the application restarts.
# --- END OF MODIFIED FUNCTION ---


# --- Categorization Logic ---
# --- UPDATED HIERARCHY ---
def categorize_transaction(description: str) -> str:
    """
    Categorizes a transaction based on description using the hierarchy:
    1. User Rules
    2. Vendor Rules
    3. LLM Inferred Rules
    """
    if not description:
        return 'Uncategorized'

    desc_lower = description.lower()

    # 1. Check User Rules First (Highest Priority)
    sorted_user_keys = sorted(USER_RULES.keys(), key=len, reverse=True)
    for key in sorted_user_keys:
        if key in desc_lower:
            category = USER_RULES[key]
            log.debug(f"Matched user rule '{key}' for description '{description}'. Category: {category}")
            return category

    # 2. Check Vendor Rules (Middle Priority)
    sorted_vendor_keys = sorted(VENDOR_RULES.keys(), key=len, reverse=True)
    for key in sorted_vendor_keys:
        if key in desc_lower:
            category = VENDOR_RULES[key]
            log.debug(f"Matched vendor rule '{key}' for description '{description}'. Category: {category}")
            return category

    # 3. Check LLM Inferred Rules (Lowest Priority)
    sorted_llm_keys = sorted(LLM_RULES.keys(), key=len, reverse=True)
    for key in sorted_llm_keys:
        if key in desc_lower:
            category = LLM_RULES[key]
            log.debug(f"Matched LLM rule '{key}' for description '{description}'. Category: {category}")
            return category
    # --- END HIERARCHY UPDATE ---

    # 4. Default if no match
    log.debug(f"No rule matched for description '{description}'. Defaulting to Uncategorized.")
    return 'Uncategorized'


# --- CSV Parsing Functions ---

def parse_chase_csv_common(filepath: str, account_type: str) -> List[Transaction]:
    """Common logic for parsing Chase CSV files."""
    transactions = []
    filename = os.path.basename(filepath)
    log.info(f"Starting parsing for {account_type} file: {filename}")
    try:
        # Ensure rule sets are loaded before parsing starts
        load_user_rules() # Reload user rules from file
        # VENDOR_RULES and LLM_RULES are loaded at module import,
        # but could be reloaded here if dynamic updates are expected during runtime without restart.
        # load_llm_rules() # Uncomment if needed

        with open(filepath, mode='r', encoding='utf-8') as csvfile:
            # Use DictReader for easier column access by name
            # Handle potential variations in header names
            reader = csv.DictReader(csvfile)
            fieldnames_lower = [name.lower().strip() for name in reader.fieldnames or []]

            # Define potential variations for required columns
            date_cols = ['transaction date', 'posting date']
            desc_cols = ['description']
            amount_cols = ['amount']

            # Find the actual column names used in this file
            date_col = next((name for name in reader.fieldnames or [] if name.lower().strip() in date_cols), None)
            desc_col = next((name for name in reader.fieldnames or [] if name.lower().strip() in desc_cols), None)
            amount_col = next((name for name in reader.fieldnames or [] if name.lower().strip() in amount_cols), None)
            type_col = next((name for name in reader.fieldnames or [] if name.lower().strip() == 'type'), None) # Optional type col

            if not all([date_col, desc_col, amount_col]):
                 missing = []
                 if not date_col: missing.append("Date ('Transaction Date' or 'Posting Date')")
                 if not desc_col: missing.append("Description")
                 if not amount_col: missing.append("Amount")
                 log.error(f"CSV file {filename} is missing required columns: {', '.join(missing)}. Cannot parse.")
                 raise ValueError(f"Missing required columns in {filename}: {', '.join(missing)}")

            for i, row in enumerate(reader):
                try:
                    # Extract data using the found column names
                    date_str = row.get(date_col)
                    raw_desc = row.get(desc_col, '').strip()
                    amount_str = row.get(amount_col, '0').strip()

                    if not date_str or not raw_desc:
                        log.warning(f"Skipping row {i+1} in {filename} due to missing date or description.")
                        continue

                    # Clean description (basic example: remove extra spaces)
                    description = ' '.join(raw_desc.split())

                    # Parse date
                    try:
                        # Chase format is usually MM/DD/YYYY
                        transaction_date = dt.datetime.strptime(date_str, '%m/%d/%Y').date()
                    except ValueError:
                        log.warning(f"Skipping row {i+1} in {filename} due to invalid date format: {date_str}")
                        continue

                    # Parse amount
                    try:
                        amount = Decimal(amount_str)
                    except InvalidOperation:
                        log.warning(f"Skipping row {i+1} in {filename} due to invalid amount: {amount_str}")
                        continue

                    # Determine transaction type (simple version based on amount)
                    transaction_type_detail = row.get(type_col) if type_col else None # Get detailed type if available
                    if transaction_type_detail:
                        tx_type = transaction_type_detail.strip()
                    elif amount > 0:
                        # Refine credit type based on description if possible
                        if 'payment' in description.lower():
                            tx_type = 'PAYMENT_RECEIVED'
                        elif 'deposit' in description.lower():
                            tx_type = 'DEPOSIT'
                        else:
                            tx_type = 'CREDIT'
                    else:
                        # Refine debit type
                        if 'withdraw' in description.lower():
                            tx_type = 'WITHDRAWAL'
                        else:
                            tx_type = 'DEBIT'

                    # Categorize using the updated hierarchy
                    category = categorize_transaction(description)

                    # Create Transaction object (ID 0, will be assigned by DB)
                    transactions.append(Transaction(
                        id=0,
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
                    log.error(f"Error processing row {i+1} in {filename}: {row_error}", exc_info=True)
                    # Decide whether to skip the row or stop parsing

        log.info(f"Finished parsing {filename}. Found {len(transactions)} transactions.")
        return transactions

    except FileNotFoundError:
        log.error(f"File not found: {filepath}")
        return []
    except ValueError as ve: # Catch specific errors like missing columns
        log.error(f"Parsing error for {filename}: {ve}")
        return [] # Return empty on critical format errors
    except Exception as e:
        log.error(f"Failed to parse {filepath}: {e}", exc_info=True)
        return []


def parse_checking_csv(filepath: str) -> List[Transaction]:
    """Parses a Chase checking account CSV file."""
    return parse_chase_csv_common(filepath, 'checking')

def parse_credit_csv(filepath: str) -> List[Transaction]:
    """Parses a Chase credit card CSV file."""
    # Note: Credit card CSVs might have different column names or formats
    # Adjust the 'parse_chase_csv_common' or create a specific function if needed
    # Example differences: 'Posting Date' vs 'Transaction Date', sign of amount for payments
    return parse_chase_csv_common(filepath, 'credit')


# --- Example Usage (for testing parser.py directly) ---
if __name__ == '__main__':
    log.info("parser.py executed directly for testing.")

    # Create dummy data directory if it doesn't exist
    if not os.path.exists('data'):
        os.makedirs('data')

    # --- Create Dummy CSV Files for Testing ---
    dummy_checking_path = 'data/dummy_checking.csv'
    dummy_credit_path = 'data/dummy_credit.csv'

    checking_data = [
        ['Transaction Date', 'Posting Date', 'Description', 'Amount', 'Type', 'Balance', 'Check or Slip No.'],
        ['03/15/2025', '03/15/2025', 'PAYROLL DEPOSIT - COMPANY ABC', '2000.00', 'ACH_CREDIT', '5000.00', ''],
        ['03/10/2025', '03/11/2025', 'GROCERY STORE PURCHASE', '-75.50', 'DEBIT_CARD', '3000.00', ''],
        ['03/05/2025', '03/05/2025', 'Payment Thank You-Mobile', '-819.17', 'ACH_DEBIT', '3075.50', ''], # Payment TO credit card
        ['INVALID_DATE', '03/01/2025', 'Test Invalid Date', '-10.00', 'DEBIT_CARD', '3894.67', ''],
        ['03/01/2025', '03/01/2025', 'Test Invalid Amount', 'INVALID', 'DEBIT_CARD', '3904.67', '']
    ]
    credit_data = [
         # Note: Chase credit often uses 'Posting Date' and positive amounts for payments received
        ['Transaction Date', 'Posting Date', 'Description', 'Category', 'Type', 'Amount', 'Memo'],
        ['04/10/2025', '04/11/2025', 'ONLINE PAYMENT - THANK YOU', 'Payment', 'Payment', '500.00', ''], # Payment received
        ['04/08/2025', '04/09/2025', 'RESTAURANT XYZ', 'Food & Drink', 'Sale', '-65.20', ''],
        ['04/05/2025', '04/06/2025', 'AMAZON PRIME VIDEO', 'Shopping', 'Sale', '-14.99', '']
    ]

    try:
        with open(dummy_checking_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(checking_data)
        with open(dummy_credit_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(credit_data)
        log.info("Created dummy CSV files for testing.")
    except IOError as e:
        log.error(f"Failed to create dummy CSV files: {e}")

    # --- Test Parsing ---
    print("\n--- Testing Checking Parser ---")
    checking_tx = parse_checking_csv(dummy_checking_path)
    for tx in checking_tx:
        print(tx.to_dict())

    print("\n--- Testing Credit Parser ---")
    credit_tx = parse_credit_csv(dummy_credit_path)
    for tx in credit_tx:
        print(tx.to_dict())

    # --- Test Rule Management ---
    print("\n--- Testing Rule Management ---")
    # Create dummy rule files if they don't exist
    if not os.path.exists(USER_RULES_FILE):
        with open(USER_RULES_FILE, 'w') as f: json.dump({"payment thank you-mobile": "Payments"}, f) # Add initial user rule
    if not os.path.exists(LLM_RULES_FILE):
        with open(LLM_RULES_FILE, 'w') as f: json.dump({"amazon prime video": "Subscriptions"}, f) # Add initial LLM rule

    load_user_rules() # Load potentially existing rules
    load_llm_rules()
    print("Initial User Rules:", USER_RULES)
    print("Initial LLM Rules:", LLM_RULES)
    add_user_rule(" grocery store purchase ", "Groceries") # Test adding user rule
    save_llm_rule(" restaurant xyz ", "Food") # Test adding LLM rule
    print("User Rules after add:", USER_RULES)
    print("LLM Rules after add:", LLM_RULES)

    # Test categorization hierarchy
    print("\n--- Testing Categorization Hierarchy ---")
    print("Categorizing 'GROCERY STORE PURCHASE':", categorize_transaction('GROCERY STORE PURCHASE')) # Should use User Rule
    print("Categorizing 'RESTAURANT XYZ':", categorize_transaction('RESTAURANT XYZ')) # Should use LLM Rule (if User/Vendor don't match)
    print("Categorizing 'PAYROLL DEPOSIT - COMPANY ABC':", categorize_transaction('PAYROLL DEPOSIT - COMPANY ABC')) # Should use Vendor Rule (assuming 'payroll' is in vendors.json)
    print("Categorizing 'Payment Thank You-Mobile':", categorize_transaction('Payment Thank You-Mobile')) # Should use initial User Rule


    # Test clearing rules (only memory now)
    clear_user_rules()
    print("\nUser Rules after clear (memory only):", USER_RULES)
    load_user_rules() # Load back from file to show persistence
    print("User Rules after reload from file:", USER_RULES)


    # Clean up dummy files
    # try:
    #     if os.path.exists(dummy_checking_path): os.remove(dummy_checking_path)
    #     if os.path.exists(dummy_credit_path): os.remove(dummy_credit_path)
    #     log.info("Cleaned up dummy CSV files.")
    # except OSError as e:
    #     log.error(f"Error cleaning up dummy files: {e}")

