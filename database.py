import sqlite3
import logging
import datetime as dt
import json
import re # Import regular expression module
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Dict

# Import Transaction class from parser
from parser import Transaction # Assuming parser.py is correct and available

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATABASE_FILE = BASE_DIR / 'spendlens.db'
USER_RULES_FILE = BASE_DIR / 'user_rules.json'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [DATABASE] %(message)s')

# --- Helper Function for Cleaning ---
def _clean_description_for_rule(description: str) -> str:
    """
    Cleans a transaction description to create a more general key for user rules.
    Removes common date patterns (MM/DD, MM/DD/YY(YY)) from the end and trims whitespace.
    """
    if not description:
        return ""
    # Regex: Optional whitespace (\s*), then MM/DD, optionally followed by /YY or /YYYY (\/\d{2,4})?,
    # surrounded by optional whitespace, anchored to the end of the string ($).
    # Also handle potential extra spaces before the date pattern.
    # Example patterns to remove: " 04/27", " 04/27/2025 ", " 4/27 "
    cleaned = re.sub(r'\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*$', '', description)
    # Remove trailing transaction/reference numbers if they follow common patterns (optional refinement)
    # cleaned = re.sub(r'\s+\d+$', '', cleaned) # Remove trailing numbers
    # cleaned = re.sub(r'\s+[a-zA-Z0-9]{8,}$', '', cleaned) # Remove long trailing alphanumeric codes
    return cleaned.strip()


# --- Database Initialization ---
# (init_db function remains the same)
def init_db(db_path: Path = DATABASE_FILE):
    """Initializes the database."""
    conn = None
    try:
        logging.info(f"Attempting to connect/create database at: {db_path}")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        logging.info(f"Executing CREATE TABLE IF NOT EXISTS for transactions.")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                category TEXT, -- Stored lowercase
                transaction_type TEXT,
                source_account_type TEXT,
                source_filename TEXT,
                raw_description TEXT
            )
        ''')
        conn.commit()
        logging.info(f"Database table 'transactions' ensured/created successfully.")
    except sqlite3.Error as e:
        logging.error(f"Database error during initialization: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logging.info(f"Database connection closed after init.")

# --- Database Operations ---
# (add_transactions remains the same)
def add_transactions(transactions: List[Transaction], db_path: Path = DATABASE_FILE, clear_existing: bool = True):
    """Adds a list of Transaction objects to the database, storing categories lowercase."""
    logging.info(f"add_transactions called. clear_existing={clear_existing}. Number of input transactions: {len(transactions)}")
    if not transactions and not clear_existing:
        logging.info("No transactions provided and clear_existing is False. Nothing to do.")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()

        if clear_existing:
            logging.info("Executing DELETE FROM transactions...")
            cursor.execute("DELETE FROM transactions")
            logging.info("Cleared existing transactions from the database.")
            if not transactions:
                conn.commit()
                logging.info("Committed clear operation (no new transactions to add).")
                return

        data_to_insert = []
        valid_count = 0
        skipped_count = 0
        for tx in transactions:
            if not isinstance(tx.date, dt.date) or not isinstance(tx.amount, Decimal):
                logging.warning(f"Skipping transaction due to invalid type: Date={type(tx.date)}, Amount={type(tx.amount)} | TX: {tx}")
                skipped_count += 1
                continue
            category_lower = tx.category.lower() if tx.category else None
            data_to_insert.append((
                tx.date.isoformat(), str(tx.amount), tx.description, category_lower,
                tx.transaction_type, tx.source_account_type, tx.source_filename, tx.raw_description
            ))
            valid_count += 1

        if skipped_count > 0: logging.warning(f"Skipped {skipped_count} transactions during preparation.")
        if not data_to_insert:
            logging.warning("No valid transactions found to insert after type checking.")
            if clear_existing: conn.commit()
            return

        logging.info(f"Attempting to insert {len(data_to_insert)} valid transactions...")
        cursor.executemany('''
            INSERT INTO transactions (
                date, amount, description, category, transaction_type,
                source_account_type, source_filename, raw_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_to_insert)
        logging.info(f"Insertion executed. Row count affected (approx): {cursor.rowcount}")
        conn.commit()
        logging.info(f"Committed {len(data_to_insert)} transactions successfully.")

    except sqlite3.Error as e:
        logging.error(f"Database error adding transactions: {e}", exc_info=True)
        if conn: conn.rollback(); logging.info("Rolled back transaction due to error.")
    finally:
        if conn: conn.close(); logging.info("Database connection closed after add_transactions.")


# (get_all_transactions remains the same)
def get_all_transactions(db_path: Path = DATABASE_FILE) -> List[Transaction]:
    """Retrieves all transactions from the database including their IDs."""
    transactions: List[Transaction] = []
    conn = None
    logging.info(f"get_all_transactions called. Connecting to {db_path}")
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()

        logging.info("Executing SELECT FROM transactions...")
        cursor.execute("SELECT id, date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description FROM transactions ORDER BY date, id")
        rows = cursor.fetchall()
        logging.info(f"Fetched {len(rows)} rows from the database.")
        if not rows: return []

        converted_count = 0
        conversion_errors = 0
        for i, row in enumerate(rows):
            try:
                (tx_id, date_str, description, amount_str, category_db, trans_type,
                 acc_type, filename, raw_desc) = row
                transaction = Transaction(
                    id=tx_id, date=dt.date.fromisoformat(date_str), description=description,
                    amount=Decimal(amount_str), category=category_db if category_db else "Uncategorized",
                    transaction_type=trans_type, source_account_type=acc_type,
                    source_filename=filename, raw_description=raw_desc
                )
                transactions.append(transaction)
                converted_count += 1
            except (ValueError, TypeError, InvalidOperation) as e:
                logging.warning(f"Skipping row {i+1} (ID: {row[0] if row else 'N/A'}) due to data conversion error: {e} | Row: {row}")
                conversion_errors += 1
            except Exception as e:
                 logging.error(f"Unexpected error converting row {i+1} (ID: {row[0] if row else 'N/A'}) to Transaction: {e} | Row: {row}")
                 conversion_errors += 1

        logging.info(f"Successfully converted {converted_count} rows to Transaction objects.")
        if conversion_errors > 0: logging.warning(f"Encountered errors converting {conversion_errors} rows.")

    except sqlite3.Error as e:
        logging.error(f"Database error retrieving transactions: {e}", exc_info=True)
    finally:
        if conn: conn.close(); logging.info("Database connection closed after get_all_transactions.")

    return transactions

# (update_transaction_category remains the same)
def update_transaction_category(transaction_id: int, new_category: str, db_path: Path = DATABASE_FILE) -> bool:
    """Updates the category (stored lowercase) of a specific transaction."""
    conn = None
    success = False
    category_lower = new_category.strip().lower()
    if not category_lower:
        logging.warning("Attempted to update category to an empty string. Update cancelled.")
        return False

    logging.info(f"Attempting to update category for transaction ID {transaction_id} to '{category_lower}' (lowercase) in {db_path}")
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE transactions SET category = ? WHERE id = ?", (category_lower, transaction_id))
        if cursor.rowcount == 1:
            conn.commit()
            success = True
            logging.info(f"Successfully updated category for transaction ID {transaction_id}.")
        elif cursor.rowcount == 0:
             logging.warning(f"No transaction found with ID {transaction_id}. Update failed.")
        else:
            logging.error(f"Unexpected number of rows affected ({cursor.rowcount}) for ID {transaction_id}. Rolling back.")
            conn.rollback()
    except sqlite3.Error as e:
        logging.error(f"Database error updating category for ID {transaction_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn: conn.close(); logging.info("Database connection closed after update_transaction_category.")
    return success

# (load_user_rules remains the same)
def load_user_rules(rules_path: Path = USER_RULES_FILE) -> Dict[str, str]:
    """Loads user-defined category rules from a JSON file."""
    if not rules_path.exists():
        logging.info(f"User rules file not found at {rules_path}. Returning empty ruleset.")
        return {}
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
            rules_lower = {k.lower(): v for k, v in rules.items()}
            logging.info(f"Loaded {len(rules_lower)} user rules from {rules_path}.")
            return rules_lower
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from user rules file: {rules_path}. Returning empty ruleset.")
        return {}
    except Exception as e:
        logging.error(f"Error loading user rules file {rules_path}: {e}", exc_info=True)
        return {}

# --- Change: Update User Rule Saving ---
def save_user_rule(description: str, category: str, rules_path: Path = USER_RULES_FILE):
    """Adds or updates a rule in the user_rules.json file after cleaning the description."""
    if not description or not category:
        logging.warning("Attempted to save user rule with empty description or category. Aborting.")
        return

    # --- Change: Clean the description before using it as a key ---
    cleaned_description = _clean_description_for_rule(description)
    if not cleaned_description:
        logging.warning(f"Description '{description}' resulted in empty string after cleaning. Cannot save rule.")
        return

    # Use cleaned, lowercased description as key; keep original category case for value
    rule_key = cleaned_description.lower()
    rule_value = category.strip() # Use the category exactly as provided by user

    logging.info(f"Attempting to save user rule: '{rule_key}' -> '{rule_value}' to {rules_path}")
    try:
        user_rules = load_user_rules(rules_path) # Loads with lowercase keys
        user_rules[rule_key] = rule_value # Add/update rule

        # Save back to the file
        with open(rules_path, 'w', encoding='utf-8') as f:
            json.dump(user_rules, f, indent=4, ensure_ascii=False)
        logging.info(f"Successfully saved user rule to {rules_path}.")

    except Exception as e:
        logging.error(f"Error saving user rule to {rules_path}: {e}", exc_info=True)

# (get_transaction_by_id remains the same)
def get_transaction_by_id(transaction_id: int, db_path: Path = DATABASE_FILE) -> Optional[Transaction]:
    """Retrieves a single transaction by its ID."""
    conn = None
    transaction = None
    logging.info(f"Attempting to fetch transaction ID {transaction_id} from {db_path}")
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description FROM transactions WHERE id = ?", (transaction_id,))
        row = cursor.fetchone()
        if row:
            logging.info(f"Found transaction for ID {transaction_id}.")
            try:
                (tx_id, date_str, description, amount_str, category_db, trans_type,
                 acc_type, filename, raw_desc) = row
                transaction = Transaction(
                    id=tx_id, date=dt.date.fromisoformat(date_str), description=description,
                    amount=Decimal(amount_str), category=category_db if category_db else "Uncategorized",
                    transaction_type=trans_type, source_account_type=acc_type,
                    source_filename=filename, raw_description=raw_desc
                )
            except Exception as e:
                 logging.error(f"Error converting row to Transaction for ID {transaction_id}: {e} | Row: {row}")
        else:
            logging.warning(f"No transaction found for ID {transaction_id}.")
    except sqlite3.Error as e:
        logging.error(f"Database error retrieving transaction ID {transaction_id}: {e}", exc_info=True)
    finally:
        if conn: conn.close(); logging.info("Database connection closed after get_transaction_by_id.")
    return transaction

# (Testing block remains the same)
if __name__ == '__main__':
    # ... (rest of the testing code remains the same) ...
    print("Initializing Database...")
    init_db() # Ensure DB and table exist

    print("\nClearing any existing test data...")
    add_transactions([], clear_existing=True)

    print("\nCreating dummy transactions...")
    dummy_txs = [
        Transaction(date=dt.date(2024, 4, 1), description="Test Income 04/01", amount=Decimal("100.00"), category="Income", id=None),
        Transaction(date=dt.date(2024, 4, 2), description="Test Spending 04/02/2024", amount=Decimal("-25.50"), category="Food", id=None),
    ]
    print("\nAdding dummy transactions...")
    add_transactions(dummy_txs, clear_existing=True) # Add and clear

    print("\nFetching transactions after adding...")
    fetched_txs = get_all_transactions()
    if fetched_txs:
        print(f"Found {len(fetched_txs)} transactions:")
        for tx in fetched_txs: print(tx)

        # Test update and rule saving
        tx_to_update = fetched_txs[1] # Get the second transaction (Test Spending)
        print(f"\nAttempting to update transaction ID {tx_to_update.id} from '{tx_to_update.category}' to 'Dining Out'...")
        update_success = update_transaction_category(tx_to_update.id, "Dining Out")
        print(f"Update successful: {update_success}")

        if update_success:
             print(f"\nAttempting to save user rule for description '{tx_to_update.description}' -> 'Dining Out'")
             # Manually call save_user_rule for testing (app.py does this automatically)
             save_user_rule(tx_to_update.description, "Dining Out")
             print(f"Check '{USER_RULES_FILE.name}' to verify the rule (key should be cleaned).")

        print("\nFetching transactions after update...")
        updated_txs = get_all_transactions()
        print(f"Found {len(updated_txs)} transactions:")
        for tx in updated_txs: print(tx)
    else:
        print("No transactions found to test.")

