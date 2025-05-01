# database.py

import sqlite3
import logging
from decimal import Decimal
import datetime as dt
from typing import List, Optional, Tuple, Dict, Any

# Configure logging
log = logging.getLogger('database') # Use specific logger name
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

DATABASE_NAME = 'spendlens.db'

# Define the Transaction class structure (can be imported or defined here)
# Ensure this matches the structure used elsewhere (e.g., parser.py)
class Transaction:
    def __init__(self, id: int, date: dt.date, description: str, amount: Decimal,
                 category: str, transaction_type: Optional[str] = None,
                 source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None,
                 raw_description: Optional[str] = None):
        self.id = id
        self.date = date
        self.description = description
        self.amount = amount
        self.category = category
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type
        self.source_filename = source_filename
        self.raw_description = raw_description if raw_description else description # Fallback

    def to_dict(self) -> Dict[str, Any]:
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

    @classmethod
    def from_row(cls, row: Tuple) -> 'Transaction':
        """Creates a Transaction object from a database row tuple."""
        (id, date_str, description, amount_str, category, transaction_type,
         source_account_type, source_filename, raw_description) = row

        date_obj = dt.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        # Convert amount string back to Decimal, handle potential None
        amount_dec = Decimal(amount_str) if amount_str is not None else Decimal('0')

        return cls(
            id=id,
            date=date_obj,
            description=description,
            amount=amount_dec,
            category=category,
            transaction_type=transaction_type,
            source_account_type=source_account_type,
            source_filename=source_filename,
            raw_description=raw_description
        )


def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    log.debug(f"Attempting to connect to database: {DATABASE_NAME}")
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        conn.row_factory = sqlite3.Row # Optional: access columns by name
        log.debug("Database connection successful.")
        return conn
    except sqlite3.Error as e:
        log.error(f"Error connecting to database {DATABASE_NAME}: {e}", exc_info=True)
        raise # Re-raise the exception after logging

def close_db_connection(conn: Optional[sqlite3.Connection], context: str = "general"):
    """Closes the database connection if it's open."""
    if conn:
        try:
            conn.close()
            log.debug(f"Database connection closed after {context}.")
        except sqlite3.Error as e:
            log.error(f"Error closing database connection after {context}: {e}", exc_info=True)

def initialize_database():
    """Initializes the database by creating the transactions table if it doesn't exist."""
    log.info("Initializing database...")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL, -- Store as TEXT, handle conversion in Python
                category TEXT NOT NULL DEFAULT 'Uncategorized',
                transaction_type TEXT,
                source_account_type TEXT, -- e.g., 'checking', 'credit'
                source_filename TEXT,
                raw_description TEXT
            )
        ''')
        # Add index for faster date filtering
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category)')
        conn.commit()
        log.info("Database initialized successfully (transactions table checked/created).")
    except sqlite3.Error as e:
        log.error(f"Error initializing database: {e}", exc_info=True)
    finally:
        close_db_connection(conn, "initialize_database")

def clear_transactions():
    """Removes all transactions from the database."""
    log.warning("Clearing all transactions from the database.")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM transactions')
        conn.commit()
        log.info("Transactions table cleared successfully.")
        # Reset autoincrement counter (optional, specific to SQLite)
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='transactions'")
        conn.commit()
        log.info("Autoincrement counter for transactions reset.")
    except sqlite3.Error as e:
        log.error(f"Error clearing transactions: {e}", exc_info=True)
    finally:
        close_db_connection(conn, "clear_transactions")

def save_transactions(transactions: List[Transaction]):
    """Saves a list of Transaction objects to the database."""
    if not transactions:
        log.info("No transactions provided to save.")
        return

    log.info(f"Attempting to save {len(transactions)} transactions...")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Prepare data for executemany - convert Decimal to string for storage
        data_to_save = [
            (t.date.isoformat(), t.description, str(t.amount), t.category,
             t.transaction_type, t.source_account_type, t.source_filename,
             t.raw_description)
            for t in transactions if t.date is not None # Ensure date is not None
        ]

        if not data_to_save:
            log.warning("No valid transactions (with dates) found to save after filtering.")
            return

        cursor.executemany('''
            INSERT INTO transactions (date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_to_save)
        conn.commit()
        log.info(f"Successfully saved {len(data_to_save)} transactions.")
    except sqlite3.Error as e:
        log.error(f"Error saving transactions: {e}", exc_info=True)
        # Consider rolling back if needed, though commit might have partially succeeded
    finally:
        close_db_connection(conn, "save_transactions")

def update_transaction_category(transaction_id: int, new_category: str):
    """Updates the category of a specific transaction."""
    log.info(f"Attempting to update category for transaction ID {transaction_id} to '{new_category}'")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions
            SET category = ?
            WHERE id = ?
        ''', (new_category, transaction_id))
        conn.commit()
        if cursor.rowcount > 0:
            log.info(f"Successfully updated category for transaction ID {transaction_id}.")
            return True
        else:
            log.warning(f"Transaction ID {transaction_id} not found for category update.")
            return False
    except sqlite3.Error as e:
        log.error(f"Error updating category for transaction ID {transaction_id}: {e}", exc_info=True)
        return False
    finally:
        close_db_connection(conn, f"update_transaction_category (ID: {transaction_id})")

def get_all_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None) -> List[Transaction]:
    """Retrieves all transactions, optionally filtered by date range and category."""
    log.info("get_all_transactions called.")
    conn = None
    transactions = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = '''
            SELECT id, date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description
            FROM transactions
        '''
        params = []
        conditions = []

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
            log.info(f"Filtering transactions from date: {start_date}")
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)
            log.info(f"Filtering transactions up to date: {end_date}")
        if category:
             conditions.append("category = ?")
             params.append(category)
             log.info(f"Filtering transactions by category: {category}")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY date, id" # Ensure consistent ordering

        log.info(f"Executing SQL: {query} with params: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        log.info(f"Fetched {len(rows)} rows from the database matching filters.")

        transactions = [Transaction.from_row(row) for row in rows]
        log.info(f"Successfully converted {len(transactions)} rows.")

    except sqlite3.Error as e:
        log.error(f"Error retrieving transactions: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Unexpected error converting transaction rows: {e}", exc_info=True)
    finally:
        close_db_connection(conn, "get_all_transactions")

    return transactions

# --- NEW FUNCTION ---
def calculate_total_for_period(
    start_date: str,
    end_date: str,
    category: Optional[str] = None,
    exclude_categories: Optional[List[str]] = None,
    transaction_type: Optional[str] = None # e.g., 'income' or 'spending'
    ) -> Decimal:
    """
    Calculates the sum of transaction amounts for a given period,
    optionally filtered by category and transaction type (income/spending),
    and allowing category exclusions.

    Args:
        start_date: Start date string (YYYY-MM-DD).
        end_date: End date string (YYYY-MM-DD).
        category: Specific category to filter by (optional).
        exclude_categories: List of categories to exclude (optional).
        transaction_type: Filter by 'income' (amount > 0) or 'spending' (amount < 0) (optional).

    Returns:
        The calculated total as a Decimal, or Decimal('0') if no matching transactions.
    """
    log.info(f"Calculating total for period {start_date} to {end_date}")
    if category: log.info(f"Filtering by category: {category}")
    if exclude_categories: log.info(f"Excluding categories: {exclude_categories}")
    if transaction_type: log.info(f"Filtering by transaction type: {transaction_type}")

    conn = None
    total = Decimal('0')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query to sum amounts. Note: SQLite SUM returns NULL if no rows match, handle this.
        # Also, need to cast amount TEXT to REAL/NUMERIC for summation.
        query = "SELECT SUM(CAST(amount AS REAL)) FROM transactions WHERE date >= ? AND date <= ?"
        params: List[Any] = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        if exclude_categories:
            # Create placeholders for each excluded category
            placeholders = ', '.join('?' * len(exclude_categories))
            query += f" AND category NOT IN ({placeholders})"
            params.extend(exclude_categories)

        if transaction_type == 'income':
            # Filter for positive amounts (CAST needed)
            query += " AND CAST(amount AS REAL) > 0"
        elif transaction_type == 'spending':
            # Filter for negative amounts (CAST needed)
            query += " AND CAST(amount AS REAL) < 0"

        log.info(f"Executing SQL for calculation: {query} with params: {params}")
        cursor.execute(query, params)
        result = cursor.fetchone()

        # fetchone() returns a tuple, e.g., (Decimal('123.45'),) or (None,) if no rows/sum is null
        if result and result[0] is not None:
            # Convert the result (which might be float from REAL cast) to Decimal
            total = Decimal(str(result[0]))
            log.info(f"Calculated total: {total:.2f}")
        else:
            log.info("No matching transactions found or sum is NULL. Total is 0.")
            total = Decimal('0')

    except sqlite3.Error as e:
        log.error(f"Error calculating total: {e}", exc_info=True)
        total = Decimal('0') # Return 0 on error
    except Exception as e:
        log.error(f"Unexpected error during calculation: {e}", exc_info=True)
        total = Decimal('0')
    finally:
        close_db_connection(conn, "calculate_total_for_period")

    return total
# --- END OF NEW FUNCTION ---

# Example usage (optional, for testing database.py directly)
if __name__ == "__main__":
    log.info("database.py executed directly for testing.")
    initialize_database()

    # --- Example: Clear and Save ---
    # clear_transactions()
    # test_transactions = [
    #     Transaction(id=0, date=dt.date(2025, 3, 7), description="Payroll", amount=Decimal("2100.50"), category="Income"),
    #     Transaction(id=0, date=dt.date(2025, 3, 5), description="CC Payment", amount=Decimal("800.00"), category="Payments"),
    #     Transaction(id=0, date=dt.date(2025, 3, 10), description="Groceries", amount=Decimal("-150.25"), category="Food"),
    #     Transaction(id=0, date=dt.date(2025, 4, 8), description="Payroll", amount=Decimal("2150.75"), category="Income"),
    #     Transaction(id=0, date=dt.date(2025, 4, 12), description="Gas", amount=Decimal("-55.00"), category="Gas"),
    # ]
    # save_transactions(test_transactions)

    # --- Example: Get Transactions ---
    log.info("\n--- Getting all transactions for March 2025 ---")
    march_tx = get_all_transactions(start_date="2025-03-01", end_date="2025-03-31")
    for tx in march_tx:
        log.info(tx.to_dict())

    # --- Example: Calculate Totals ---
    log.info("\n--- Calculating Income for March 2025 (excluding Payments) ---")
    march_income = calculate_total_for_period(
        start_date="2025-03-01",
        end_date="2025-03-31",
        # category="Income", # Can specify category here
        transaction_type='income', # Or filter by positive amount
        exclude_categories=["Payments", "Transfers"] # Explicitly exclude
    )
    log.info(f"Calculated March Income: {march_income:.2f}")

    log.info("\n--- Calculating Spending for March 2025 ---")
    march_spending = calculate_total_for_period(
        start_date="2025-03-01",
        end_date="2025-03-31",
        transaction_type='spending' # Filter by negative amount
    )
    # Spending total will be negative, use abs() if you want positive representation
    log.info(f"Calculated March Spending: {march_spending:.2f}")

    log.info("\n--- Calculating Food Spending for March 2025 ---")
    march_food_spending = calculate_total_for_period(
        start_date="2025-03-01",
        end_date="2025-03-31",
        category="Food",
        transaction_type='spending'
    )
    log.info(f"Calculated March Food Spending: {march_food_spending:.2f}")

