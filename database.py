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

# --- Data Classes ---
# Using classes makes passing data around cleaner

class User:
    """Represents a user in the system."""
    def __init__(self, id: int, username: str, password_hash: str):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        # Attributes needed by Flask-Login
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        """Returns the user ID as a string (required by Flask-Login)."""
        return str(self.id)

    @classmethod
    def from_row(cls, row: Tuple) -> Optional['User']:
        """Creates a User object from a database row tuple."""
        if not row:
            return None
        (id_val, username, password_hash) = row
        return cls(id=id_val, username=username, password_hash=password_hash)


class Transaction:
    """Represents a transaction, now linked to a user."""
    def __init__(self, id: int, user_id: int, date: dt.date, description: str, amount: Decimal,
                 category: str, transaction_type: Optional[str] = None,
                 source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None,
                 raw_description: Optional[str] = None):
        self.id = id
        self.user_id = user_id # Link to user
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
            "user_id": self.user_id, # Include user_id
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
        # Adjust tuple unpacking based on the new table structure
        (id_val, user_id, date_str, description, amount_str, category, transaction_type,
         source_account_type, source_filename, raw_description) = row

        date_obj = dt.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        amount_dec = Decimal(amount_str) if amount_str is not None else Decimal('0')

        return cls(
            id=id_val,
            user_id=user_id, # Add user_id
            date=date_obj,
            description=description,
            amount=amount_dec,
            category=category,
            transaction_type=transaction_type,
            source_account_type=source_account_type,
            source_filename=source_filename,
            raw_description=raw_description
        )

# --- Database Connection ---

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    log.debug(f"Attempting to connect to database: {DATABASE_NAME}")
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        # conn.row_factory = sqlite3.Row # Use default tuple factory for consistency
        log.debug("Database connection successful.")
        return conn
    except sqlite3.Error as e:
        log.error(f"Error connecting to database {DATABASE_NAME}: {e}", exc_info=True)
        raise

def close_db_connection(conn: Optional[sqlite3.Connection], context: str = "general"):
    """Closes the database connection if it's open."""
    if conn:
        try:
            conn.close()
            log.debug(f"Database connection closed after {context}.")
        except sqlite3.Error as e:
            log.error(f"Error closing database connection after {context}: {e}", exc_info=True)

# --- Database Initialization (Schema Update) ---

def initialize_database():
    """Initializes the database by creating tables if they don't exist."""
    log.info("Initializing database...")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        log.info("Checked/Created 'users' table.")

        # Transactions Table (Added user_id FOREIGN KEY)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, -- Link to the user
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Uncategorized',
                transaction_type TEXT,
                source_account_type TEXT,
                source_filename TEXT,
                raw_description TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) -- Define foreign key constraint
            )
        ''')
        log.info("Checked/Created 'transactions' table with user_id.")

        # User Rules Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description_key TEXT NOT NULL, -- Lowercase description fragment
                category TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, description_key) -- Ensure one rule per key per user
            )
        ''')
        log.info("Checked/Created 'user_rules' table.")

        # LLM Rules Table (Storing suggestions per user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description_key TEXT NOT NULL, -- Lowercase description fragment
                category TEXT NOT NULL,
                -- Optional: Add confidence score or status if needed later
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, description_key) -- Ensure one suggestion per key per user
            )
        ''')
        log.info("Checked/Created 'llm_rules' table.")

        # --- ADDED FEEDBACK TABLES ---
        # Table for LLM queries that failed or couldn't be answered
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_failed_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                llm_response TEXT, -- Store the problematic response
                reason TEXT, -- e.g., 'cannot answer', 'safety block', 'error'
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        log.info("Checked/Created 'llm_failed_queries' table.")

        # Table for user reports of incorrect LLM answers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS llm_user_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                incorrect_llm_response TEXT NOT NULL,
                user_comment TEXT, -- Optional comment from user
                status TEXT DEFAULT 'pending', -- e.g., pending, reviewed, resolved
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        log.info("Checked/Created 'llm_user_reports' table.")

        # Table for general user feedback
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, -- Can be anonymous feedback
                timestamp TEXT NOT NULL,
                feedback_type TEXT, -- e.g., 'bug', 'suggestion', 'general'
                comment TEXT NOT NULL,
                contact_email TEXT, -- Optional
                status TEXT DEFAULT 'pending', -- e.g., pending, reviewed, implemented
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        log.info("Checked/Created 'user_feedback' table.")
        # --- END ADDED TABLES ---

        # Add indexes for faster lookups
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions (user_id, category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_rules_user_key ON user_rules (user_id, description_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_llm_rules_user_key ON llm_rules (user_id, description_key)')
        # Indexes for feedback tables (optional but good practice)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_llm_failed_user_time ON llm_failed_queries (user_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_llm_reports_user_time ON llm_user_reports (user_id, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_user_time ON user_feedback (user_id, timestamp)')


        conn.commit()
        log.info("Database initialization complete.")
    except sqlite3.Error as e:
        log.error(f"Error initializing database: {e}", exc_info=True)
    finally:
        close_db_connection(conn, "initialize_database")

# --- User Management Functions ---
# ... (create_user, find_user_by_username, find_user_by_id remain the same) ...
def create_user(username: str, password_hash: str) -> Optional[int]:
    log.info(f"Attempting to create user: {username}")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        conn.commit(); user_id = cursor.lastrowid; log.info(f"Created user '{username}' ID: {user_id}"); return user_id
    except sqlite3.IntegrityError: log.warning(f"Username '{username}' exists."); return None
    except sqlite3.Error as e: log.error(f"Error creating user '{username}': {e}", exc_info=True); return None
    finally: close_db_connection(conn, f"create_user ({username})")

def find_user_by_username(username: str) -> Optional[User]:
    log.debug(f"Finding user by username: {username}")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone(); return User.from_row(row) if row else None
    except sqlite3.Error as e: log.error(f"Error finding user '{username}': {e}", exc_info=True); return None
    finally: close_db_connection(conn, f"find_user_by_username ({username})")

def find_user_by_id(user_id: int) -> Optional[User]:
    log.debug(f"Finding user by ID: {user_id}")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone(); return User.from_row(row) if row else None
    except sqlite3.Error as e: log.error(f"Error finding user ID {user_id}: {e}", exc_info=True); return None
    finally: close_db_connection(conn, f"find_user_by_id ({user_id})")


# --- Transaction Management (User-Aware) ---
# ... (clear_transactions_for_user, save_transactions, update_transaction_category,
#      get_all_transactions, calculate_total_for_period remain the same) ...
def clear_transactions_for_user(user_id: int):
    log.warning(f"Clearing transactions for user_id {user_id}.")
    conn = None
    try: conn = get_db_connection(); cursor = conn.cursor(); cursor.execute('DELETE FROM transactions WHERE user_id = ?', (user_id,)); conn.commit(); log.info(f"Transactions cleared for user_id {user_id}.")
    except sqlite3.Error as e: log.error(f"Error clearing transactions for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"clear_transactions_for_user ({user_id})")

def save_transactions(user_id: int, transactions: List[Transaction]):
    if not transactions: log.info(f"No txns for user {user_id}."); return
    log.info(f"Saving {len(transactions)} txns for user {user_id}...")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        data_to_save = [(user_id, t.date.isoformat(), t.description, str(t.amount), t.category, t.transaction_type, t.source_account_type, t.source_filename, t.raw_description) for t in transactions if t.date is not None]
        if not data_to_save: log.warning(f"No valid txns for user {user_id}."); return
        cursor.executemany('INSERT INTO transactions (user_id, date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', data_to_save)
        conn.commit(); log.info(f"Saved {len(data_to_save)} txns for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error saving txns for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"save_transactions ({user_id})")

def update_transaction_category(user_id: int, transaction_id: int, new_category: str) -> bool:
    log.info(f"User {user_id} updating category for Tx {transaction_id} to '{new_category}'")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('UPDATE transactions SET category = ? WHERE id = ? AND user_id = ?', (new_category, transaction_id, user_id))
        conn.commit(); rowcount = cursor.rowcount
        if rowcount > 0: log.info(f"Updated category for Tx {transaction_id} (User {user_id})."); return True
        else: log.warning(f"Tx {transaction_id} not found or not owned by user {user_id}."); return False
    except sqlite3.Error as e: log.error(f"Error updating category for Tx {transaction_id} (User {user_id}): {e}", exc_info=True); return False
    finally: close_db_connection(conn, f"update_tx_cat (User: {user_id}, Tx: {transaction_id})")

def get_all_transactions(user_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None, category: Optional[str] = None) -> List[Transaction]:
    log.info(f"Getting txns for user {user_id}. Filters: start={start_date}, end={end_date}, cat={category}")
    conn = None; transactions = []
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = 'SELECT id, user_id, date, description, amount, category, transaction_type, source_account_type, source_filename, raw_description FROM transactions WHERE user_id = ?'
        params: List[Any] = [user_id]; conditions = []
        if start_date: conditions.append("date >= ?"); params.append(start_date)
        if end_date: conditions.append("date <= ?"); params.append(end_date)
        if category: conditions.append("category = ?"); params.append(category)
        if conditions: query += " AND " + " AND ".join(conditions)
        query += " ORDER BY date, id"
        log.info(f"Executing SQL: {query} with params: {params}")
        cursor.execute(query, params); rows = cursor.fetchall(); log.info(f"Fetched {len(rows)} rows for user {user_id}.")
        transactions = [Transaction.from_row(row) for row in rows]; log.info(f"Converted {len(transactions)} rows for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error getting txns for user {user_id}: {e}", exc_info=True)
    except Exception as e: log.error(f"Error converting rows for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"get_all_transactions ({user_id})")
    return transactions

def calculate_total_for_period(user_id: int, start_date: str, end_date: str, category: Optional[str] = None, exclude_categories: Optional[List[str]] = None, transaction_type: Optional[str] = None) -> Decimal:
    log.info(f"Calculating total for user {user_id}, period {start_date} to {end_date}, cat={category}, exclude={exclude_categories}, type={transaction_type}")
    conn = None; total = Decimal('0')
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = "SELECT SUM(CAST(amount AS REAL)) FROM transactions WHERE user_id = ? AND date >= ? AND date <= ?"
        params: List[Any] = [user_id, start_date, end_date]
        if category: query += " AND category = ?"; params.append(category)
        if exclude_categories: placeholders = ', '.join('?' * len(exclude_categories)); query += f" AND category NOT IN ({placeholders})"; params.extend(exclude_categories)
        if transaction_type == 'income': query += " AND CAST(amount AS REAL) > 0"
        elif transaction_type == 'spending': query += " AND CAST(amount AS REAL) < 0"
        log.info(f"Executing SQL: {query} with params: {params}")
        cursor.execute(query, params); result = cursor.fetchone()
        if result and result[0] is not None: total = Decimal(str(result[0])); log.info(f"Calculated total for user {user_id}: {total:.2f}")
        else: log.info(f"No matching txns or sum is NULL for user {user_id}."); total = Decimal('0')
    except sqlite3.Error as e: log.error(f"Error calculating total for user {user_id}: {e}", exc_info=True); total = Decimal('0')
    except Exception as e: log.error(f"Unexpected error during calc for user {user_id}: {e}", exc_info=True); total = Decimal('0')
    finally: close_db_connection(conn, f"calculate_total ({user_id})")
    return total

# --- Rule Management Functions (User-Aware) ---
# ... (get_user_rules, save_user_rule, get_llm_rules, save_llm_rule, clear_llm_rules_for_user remain the same) ...
def get_user_rules(user_id: int) -> Dict[str, str]:
    log.debug(f"Loading user rules for user_id {user_id}")
    conn = None; rules = {}
    try:
        conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT description_key, category FROM user_rules WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall(); rules = {row[0]: row[1] for row in rows}; log.info(f"Loaded {len(rules)} user rules for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error loading user rules for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"get_user_rules ({user_id})")
    return rules

def save_user_rule(user_id: int, description_key: str, category: str):
    log.info(f"Saving user rule for user {user_id}: '{description_key}' -> '{category}'")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('INSERT INTO user_rules (user_id, description_key, category) VALUES (?, ?, ?) ON CONFLICT(user_id, description_key) DO UPDATE SET category = excluded.category', (user_id, description_key.lower().strip(), category))
        conn.commit(); log.info(f"Saved user rule for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error saving user rule for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"save_user_rule ({user_id})")

def get_llm_rules(user_id: int) -> Dict[str, str]:
    log.debug(f"Loading LLM rules for user {user_id}")
    conn = None; rules = {}
    try:
        conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT description_key, category FROM llm_rules WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall(); rules = {row[0]: row[1] for row in rows}; log.info(f"Loaded {len(rules)} LLM rules for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error loading LLM rules for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"get_llm_rules ({user_id})")
    return rules

def save_llm_rule(user_id: int, description_key: str, category: str):
    log.info(f"Saving LLM rule for user {user_id}: '{description_key}' -> '{category}'")
    conn = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('INSERT INTO llm_rules (user_id, description_key, category) VALUES (?, ?, ?) ON CONFLICT(user_id, description_key) DO UPDATE SET category = excluded.category', (user_id, description_key.lower().strip(), category))
        conn.commit(); log.info(f"Saved LLM rule for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error saving LLM rule for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"save_llm_rule ({user_id})")

def clear_llm_rules_for_user(user_id: int):
    log.warning(f"Clearing LLM rules for user {user_id}.")
    conn = None
    try: conn = get_db_connection(); cursor = conn.cursor(); cursor.execute('DELETE FROM llm_rules WHERE user_id = ?', (user_id,)); conn.commit(); log.info(f"LLM rules cleared for user {user_id}.")
    except sqlite3.Error as e: log.error(f"Error clearing LLM rules for user {user_id}: {e}", exc_info=True)
    finally: close_db_connection(conn, f"clear_llm_rules ({user_id})")


# --- NEW FEEDBACK FUNCTIONS ---

def log_llm_failed_query(user_id: int, query: str, llm_response: Optional[str], reason: Optional[str]):
    """Logs a query where the LLM failed or couldn't answer."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    log.info(f"Logging failed LLM query for user {user_id}. Reason: {reason}")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO llm_failed_queries (user_id, timestamp, query, llm_response, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, timestamp, query, llm_response, reason))
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Error logging failed LLM query for user {user_id}: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"log_llm_failed_query ({user_id})")

def log_llm_user_report(user_id: int, query: str, incorrect_response: str, user_comment: Optional[str]):
    """Logs a user report about an incorrect LLM response."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    log.info(f"Logging user report for incorrect LLM response from user {user_id}.")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO llm_user_reports (user_id, timestamp, query, incorrect_llm_response, user_comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, timestamp, query, incorrect_response, user_comment))
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Error logging LLM user report for user {user_id}: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"log_llm_user_report ({user_id})")

def log_user_feedback(user_id: Optional[int], feedback_type: Optional[str], comment: str, contact_email: Optional[str]):
    """Logs general user feedback."""
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    log.info(f"Logging user feedback (User: {user_id if user_id else 'Anonymous'}). Type: {feedback_type}")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_feedback (user_id, timestamp, feedback_type, comment, contact_email)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, timestamp, feedback_type, comment, contact_email))
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Error logging user feedback (User: {user_id}): {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"log_user_feedback ({user_id})")

# --- END FEEDBACK FUNCTIONS ---


# Example usage (optional, for testing database.py directly)
if __name__ == "__main__":
    log.info("database.py executed directly for testing.")
    # IMPORTANT: Running this directly will create/modify spendlens.db
    # Delete spendlens.db before running app.py if you run this test.
    initialize_database()

    # --- Example: User Creation ---
    test_user_id = create_user("feedback_test", generate_password_hash("password")) # Use werkzeug hash
    if test_user_id:
        log.info(f"Test user created with ID: {test_user_id}")
        found_user = find_user_by_id(test_user_id)
        if found_user: log.info(f"Found test user: {found_user.username}")

        # --- Example: Log Feedback ---
        log.info("\n--- Testing Feedback Logging ---")
        log_llm_failed_query(test_user_id, "How do I save money?", "I cannot provide financial advice.", "cannot answer")
        log_llm_user_report(test_user_id, "Income last month?", "$500 (Incorrect)", "Actual income was $1500")
        log_user_feedback(test_user_id, "suggestion", "Add budget tracking!", "test@example.com")
        log_user_feedback(None, "bug", "Upload button is slow.", None) # Anonymous

        log.info("Check the database file 'spendlens.db' for logged feedback.")
    else:
         log.error("Failed to create test user for further testing.")

