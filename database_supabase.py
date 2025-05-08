# database_supabase.py
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch # Ensure execute_batch is imported
from decimal import Decimal
import datetime as dt
from typing import List, Optional, Tuple, Dict, Any
import os
from collections import defaultdict # Import defaultdict

from config import settings

log = logging.getLogger('database_supabase')
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG) # Use DEBUG_MODE from settings
if not log.handlers:
    handler = logging.StreamHandler()
    # More detailed formatter for better debugging
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)


# --- Data Classes ---
class User:
    """Represents a user profile."""
    def __init__(self, id: str, email: str, username: Optional[str] = None):
        self.id = id
        self.email = email
        self.username = username if username else email.split('@')[0] # Default username from email

    @classmethod
    def from_db_row(cls, row: Dict) -> Optional['User']:
        """Creates a User object from a database row."""
        if not row:
            return None
        return cls(id=str(row.get('id')), email=row.get('email'), username=row.get('username'))


class Transaction:
    """Represents a financial transaction."""
    def __init__(self, id: Optional[int], user_id: str, date: Optional[dt.date],
                 description: Optional[str], amount: Optional[Decimal], category: Optional[str],
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 data_context: Optional[str] = 'business', # NEW PARAMETER with default for V2
                 created_at: Optional[dt.datetime] = None,
                 updated_at: Optional[dt.datetime] = None):
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
        self.client_name = client_name
        self.invoice_id = invoice_id
        self.project_id = project_id
        self.payout_source = payout_source
        self.transaction_origin = transaction_origin
        self.data_context = data_context # NEW ATTRIBUTE
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        """Converts the Transaction object to a dictionary."""
        return {
            "id": self.id, "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "description": self.description,
            "amount": str(self.amount) if self.amount is not None else None,
            "category": self.category, "transaction_type": self.transaction_type,
            "source_account_type": self.source_account_type,
            "source_filename": self.source_filename, "raw_description": self.raw_description,
            "client_name": self.client_name, "invoice_id": self.invoice_id,
            "project_id": self.project_id, "payout_source": self.payout_source,
            "transaction_origin": self.transaction_origin,
            "data_context": self.data_context, # NEW IN DICT
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_db_row(cls, row: Dict) -> 'Transaction':
        """Creates a Transaction object from a database row."""
        return cls(
            id=row.get('id'), user_id=str(row.get('user_id')), date=row.get('date'),
            description=row.get('description'),
            amount=Decimal(str(row.get('amount'))) if row.get('amount') is not None else None,
            category=row.get('category'), transaction_type=row.get('transaction_type'),
            source_account_type=row.get('source_account_type'),
            source_filename=row.get('source_filename'), raw_description=row.get('raw_description'),
            client_name=row.get('client_name'), invoice_id=row.get('invoice_id'),
            project_id=row.get('project_id'), payout_source=row.get('payout_source'),
            transaction_origin=row.get('transaction_origin'),
            data_context=row.get('data_context'), # NEW FROM ROW
            created_at=row.get('created_at'), updated_at=row.get('updated_at')
        )


# --- Database Connection ---
def get_db_connection() -> Optional[psycopg2.extensions.connection]:
    """Establishes a connection to the PostgreSQL database."""
    db_connection_string = settings.SUPABASE_DB_CONN_STRING or os.environ.get('SUPABASE_DB_CONN_STRING')
    if not db_connection_string:
        log.error("SUPABASE_DB_CONN_STRING is not set. Cannot connect to database.")
        return None
    try:
        conn = psycopg2.connect(db_connection_string)
        log.debug("Database connection successful.")
        return conn
    except psycopg2.Error as e:
        log.error(f"Error connecting to Supabase PostgreSQL database: {e}", exc_info=True)
        return None


def close_db_connection(conn: Optional[psycopg2.extensions.connection], context: str = "general_operation"):
    """Closes the database connection if it's open."""
    if conn:
        try:
            conn.close()
            log.debug(f"Database connection closed for {context}.")
        except psycopg2.Error as e:
            log.error(f"Error closing PostgreSQL connection for {context}: {e}", exc_info=True)


def initialize_database():
    """Initializes the database schema if tables don't exist."""
    log.info("Initializing database schema for PostgreSQL...")
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            log.error("Cannot initialize database: No database connection.")
            return

        with conn.cursor() as cursor:
            # User Profiles Table (references auth.users)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_profiles (
                    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(100) UNIQUE,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created user_profiles table.")

            # Transactions Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.transactions (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    description TEXT NOT NULL,
                    amount DECIMAL(19, 4) NOT NULL,
                    category VARCHAR(100) NOT NULL DEFAULT 'Uncategorized',
                    transaction_type VARCHAR(50),
                    source_account_type VARCHAR(50),
                    source_filename TEXT,
                    raw_description TEXT,
                    client_name VARCHAR(255),
                    invoice_id VARCHAR(100),
                    project_id VARCHAR(100),
                    payout_source VARCHAR(100),
                    transaction_origin VARCHAR(100),
                    data_context VARCHAR(50) NOT NULL DEFAULT 'business', -- NEW FIELD
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created transactions table with data_context.")

            # User Rules Table for categorization
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_rules (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    description_key TEXT NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    UNIQUE(user_id, description_key)
                );
            ''')
            log.debug("Checked/Created user_rules table.")

            # LLM Suggested Rules Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_rules (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    description_key TEXT NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    UNIQUE(user_id, description_key)
                );
            ''')
            log.debug("Checked/Created llm_rules table.")

            # LLM Failed Queries Log
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_failed_queries (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ NOT NULL,
                    query TEXT NOT NULL,
                    llm_response TEXT,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created llm_failed_queries table.")

            # LLM User Reports (Feedback on LLM answers)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_user_reports (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ NOT NULL,
                    query TEXT NOT NULL,
                    incorrect_llm_response TEXT NOT NULL,
                    user_comment TEXT,
                    status TEXT DEFAULT 'pending', -- e.g., pending, reviewed, resolved
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created llm_user_reports table.")

            # General User Feedback Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_feedback (
                    id SERIAL PRIMARY KEY,
                    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL, -- Optional user link
                    timestamp TIMESTAMPTZ NOT NULL,
                    feedback_type VARCHAR(50), -- e.g., bug, feature_request, general
                    comment TEXT NOT NULL,
                    contact_email VARCHAR(255), -- Optional
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created user_feedback table.")

            # Indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON public.transactions (user_id, date);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_context_project ON public.transactions (user_id, data_context, project_id);') # Index for data_context
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_client ON public.transactions (user_id, client_name);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_rules_user_key ON public.user_rules (user_id, description_key);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_llm_rules_user_key ON public.llm_rules (user_id, description_key);')
            log.debug("Checked/Created indexes.")

            conn.commit()
            log.info("Database initialization/schema check for PostgreSQL complete (data_context added and other checks).")
    except psycopg2.Error as e:
        log.error(f"PostgreSQL error during database initialization: {e}", exc_info=True)
        if conn:
            conn.rollback()
    except Exception as e:
        log.error(f"Unexpected error during database initialization: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        close_db_connection(conn, "initialize_database")


# --- User Profile Management ---
def get_user_profile_by_id(user_supabase_id: str) -> Optional[User]:
    """Retrieves a user profile by their Supabase Auth ID."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, email, username FROM public.user_profiles WHERE id = %s", (user_supabase_id,))
            row = cursor.fetchone()
            log.debug(f"Fetched profile for user {user_supabase_id}: {'Found' if row else 'Not found'}")
            return User.from_db_row(row) if row else None
    except psycopg2.Error as e:
        log.error(f"DB error fetching profile for user {user_supabase_id}: {e}", exc_info=True)
        return None
    finally:
        close_db_connection(conn, f"get_user_profile_by_id for {user_supabase_id}")


def create_user_profile(user_supabase_id: str, email: str, username: Optional[str] = None) -> Optional[User]:
    """Creates a new user profile or returns existing if ID matches."""
    conn = get_db_connection()
    if not conn:
        return None
    effective_username = username if username else email.split('@')[0]
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Insert if not exists, otherwise do nothing (ON CONFLICT (id) DO NOTHING)
            # Then, select the profile to ensure it's returned consistently
            cursor.execute(
                """
                INSERT INTO public.user_profiles (id, email, username)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email, -- Keep email updated if it changes in Supabase Auth
                    username = COALESCE(public.user_profiles.username, EXCLUDED.username), -- Preserve existing username if set
                    updated_at = NOW()
                RETURNING id, email, username;
                """,
                (user_supabase_id, email, effective_username)
            )
            created_or_updated_row = cursor.fetchone()
            conn.commit()

            if created_or_updated_row:
                log.info(f"Profile created/updated for user {user_supabase_id}, email {email}.")
                return User.from_db_row(created_or_updated_row)
            else:
                # This case should ideally not happen with RETURNING, but as a fallback:
                log.warning(f"Profile for user {user_supabase_id} not returned directly after INSERT/UPDATE. Fetching separately.")
                return get_user_profile_by_id(user_supabase_id)

    except psycopg2.Error as e:
        log.error(f"DB error creating/updating profile for user {user_supabase_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    except Exception as e:
        log.error(f"Unexpected error creating/updating profile for {user_supabase_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        close_db_connection(conn, f"create_user_profile for {user_supabase_id}")


# --- Transaction Management ---
def clear_transactions_for_user(user_id: str):
    """Deletes all transactions for a given user."""
    conn = get_db_connection()
    if not conn:
        log.error(f"User {user_id}: Cannot clear transactions, no DB connection.")
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM public.transactions WHERE user_id = %s', (user_id,))
            conn.commit()
            log.info(f"User {user_id}: Cleared all transactions ({cursor.rowcount} rows affected).")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error clearing transactions: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"clear_transactions_for_user {user_id}")


def save_transactions(user_id: str, transactions: List[Transaction]) -> int:
    """Saves a list of transactions to the database for a user."""
    if not transactions:
        log.info(f"User {user_id}: No transactions provided to save.")
        return 0
    conn = get_db_connection()
    if not conn:
        log.error(f"User {user_id}: Cannot save transactions, no DB connection.")
        return 0 # Or raise an exception

    saved_count = 0
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO public.transactions (
                         user_id, date, description, amount, category, transaction_type,
                         source_account_type, source_filename, raw_description,
                         client_name, invoice_id, project_id, payout_source, transaction_origin,
                         data_context -- NEW FIELD IN SQL
                     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""" # ADDED %s
            data_to_save = []
            for t in transactions:
                if t.date is None or t.amount is None: # Basic validation
                    log.warning(f"User {user_id}: Skipping transaction due to missing date or amount: {t.description[:50] if t.description else 'N/A'}")
                    continue
                data_to_save.append((
                    user_id, t.date, t.description, t.amount, t.category,
                    t.transaction_type, t.source_account_type, t.source_filename, t.raw_description,
                    t.client_name, t.invoice_id, t.project_id, t.payout_source, t.transaction_origin,
                    t.data_context if t.data_context else 'business' # Ensure it's set, default to business
                ))

            if not data_to_save:
                log.info(f"User {user_id}: No valid transactions to save after filtering.")
                return 0

            execute_batch(cursor, sql, data_to_save)
            saved_count = len(data_to_save) # execute_batch doesn't directly return rowcount in all psycopg2 versions
            conn.commit()
            log.info(f"User {user_id}: Saved {saved_count} transactions with data_context.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error saving transactions: {e}", exc_info=True)
        if conn: conn.rollback()
        raise # Re-raise to inform the caller of the failure
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error saving transactions: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        close_db_connection(conn, f"save_transactions for {user_id}")
    return saved_count


def update_transaction_category(user_id: str, transaction_id: int, new_category: str) -> bool:
    """Updates the category of a specific transaction for a user."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE public.transactions SET category = %s, updated_at = NOW()
                              WHERE id = %s AND user_id = %s''',
                           (new_category, transaction_id, user_id))
            conn.commit()
            updated_rows = cursor.rowcount
            log.info(f"User {user_id}: Updated category for TxID {transaction_id} to '{new_category}'. Rows affected: {updated_rows}.")
            return updated_rows > 0
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error updating category for TxID {transaction_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        close_db_connection(conn, f"update_transaction_category for {user_id}, TxID {transaction_id}")


def get_transaction_by_id_for_user(user_id: str, transaction_id: int) -> Optional[Transaction]:
    """Retrieves a specific transaction by its ID for a given user."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """SELECT id, user_id, date, description, amount, category, transaction_type,
                              source_account_type, source_filename, raw_description,
                              client_name, invoice_id, project_id, payout_source, transaction_origin,
                              data_context, created_at, updated_at
                       FROM public.transactions WHERE id = %s AND user_id = %s"""
            cursor.execute(query, (transaction_id, user_id))
            row = cursor.fetchone()
            return Transaction.from_db_row(row) if row else None
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching TxID {transaction_id}: {e}", exc_info=True)
        return None
    finally:
        close_db_connection(conn, f"get_transaction_by_id_for_user {user_id}, TxID {transaction_id}")


def get_all_transactions(user_id: str, start_date: Optional[dt.date] = None,
                         end_date: Optional[dt.date] = None, category: Optional[str] = None,
                         transaction_origin: Optional[str] = None, client_name: Optional[str] = None,
                         data_context: Optional[str] = None, # NEW PARAMETER
                         project_id: Optional[str] = None     # NEW PARAMETER
                        ) -> List[Transaction]:
    """Retrieves all transactions for a user, with optional filters."""
    log.info(
        f"User {user_id}: Getting transactions. Filters: Start={start_date}, End={end_date}, Cat={category}, Origin={transaction_origin}, Client={client_name}, Context={data_context}, Project={project_id}")
    conn = get_db_connection()
    if not conn:
        return []
    transactions_list: List[Transaction] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query_parts = ["""SELECT id, user_id, date, description, amount, category, transaction_type,
                                   source_account_type, source_filename, raw_description,
                                   client_name, invoice_id, project_id, payout_source, transaction_origin,
                                   data_context, created_at, updated_at
                               FROM public.transactions WHERE user_id = %s"""]
            params: List[Any] = [user_id]

            if start_date: query_parts.append("AND date >= %s"); params.append(start_date)
            if end_date: query_parts.append("AND date <= %s"); params.append(end_date)
            if category: query_parts.append("AND category = %s"); params.append(category)
            if transaction_origin: query_parts.append("AND transaction_origin = %s"); params.append(transaction_origin)
            if client_name: query_parts.append("AND client_name ILIKE %s"); params.append(f"%{client_name}%") # Case-insensitive search
            if data_context: query_parts.append("AND data_context = %s"); params.append(data_context) # NEW FILTER
            if project_id: query_parts.append("AND project_id = %s"); params.append(project_id) # NEW FILTER

            query_parts.append("ORDER BY date DESC, created_at DESC, id DESC")
            final_query = " ".join(query_parts)

            cursor.execute(final_query, tuple(params))
            rows = cursor.fetchall()
            transactions_list = [Transaction.from_db_row(row) for row in rows]
            log.debug(f"User {user_id}: Fetched {len(transactions_list)} transactions from DB with new filters.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching transactions: {e}", exc_info=True)
        # Return empty list on error as per previous behavior, consider raising for critical errors
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error fetching transactions: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"get_all_transactions for {user_id}")
    return transactions_list


def calculate_total_for_period(user_id: str, start_date: dt.date, end_date: dt.date,
                               category: Optional[str] = None, exclude_categories: Optional[List[str]] = None,
                               transaction_type: Optional[str] = None,
                               transaction_origin: Optional[str] = None,
                               client_name: Optional[str] = None,
                               data_context: Optional[str] = None, # Added data_context
                               project_id: Optional[str] = None   # Added project_id
                               ) -> Decimal:
    """Calculates sum of transaction amounts for a period with filters."""
    log.info(
        f"User {user_id}: Calculating total. Period: {start_date}-{end_date}, Cat={category}, ExclCats={exclude_categories}, Type={transaction_type}, Origin={transaction_origin}, Client={client_name}, Context={data_context}, Project={project_id}")
    conn = get_db_connection()
    if not conn:
        return Decimal('0')
    total = Decimal('0')
    try:
        with conn.cursor() as cursor: # No RealDictCursor needed for SUM
            query_parts = ["SELECT SUM(amount) FROM public.transactions WHERE user_id = %s AND date >= %s AND date <= %s"]
            params: List[Any] = [user_id, start_date, end_date]

            if category: query_parts.append("AND category = %s"); params.append(category)
            if exclude_categories: query_parts.append("AND category NOT IN %s"); params.append(tuple(exclude_categories)) # Ensure tuple for IN
            if transaction_type == 'income': query_parts.append("AND amount > 0")
            elif transaction_type == 'spending': query_parts.append("AND amount < 0")
            if transaction_origin: query_parts.append("AND transaction_origin = %s"); params.append(transaction_origin)
            if client_name: query_parts.append("AND client_name ILIKE %s"); params.append(f"%{client_name}%")
            if data_context: query_parts.append("AND data_context = %s"); params.append(data_context)
            if project_id: query_parts.append("AND project_id = %s"); params.append(project_id)

            final_query = " ".join(query_parts)
            cursor.execute(final_query, tuple(params))
            result = cursor.fetchone()
            if result and result[0] is not None:
                total = result[0]
        log.debug(f"User {user_id}: Calculated total for period: {total}")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error calculating total for period: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"calculate_total_for_period for {user_id}")
    return total


# --- Client-Specific Functions ---
def get_unique_client_names(user_id: str, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None, data_context: Optional[str] = None) -> List[str]:
    """Fetches unique, non-null client names for a user, optionally filtered by date and data_context."""
    log.info(f"User {user_id}: Fetching unique client names. Period: {start_date} to {end_date}, Context: {data_context}")
    conn = get_db_connection()
    if not conn: return []
    client_names: List[str] = []
    try:
        with conn.cursor() as cursor:
            query_parts = ["SELECT DISTINCT client_name FROM public.transactions WHERE user_id = %s AND client_name IS NOT NULL AND client_name <> ''"]
            params: List[Any] = [user_id]
            if start_date: query_parts.append("AND date >= %s"); params.append(start_date)
            if end_date: query_parts.append("AND date <= %s"); params.append(end_date)
            if data_context: query_parts.append("AND data_context = %s"); params.append(data_context)
            query_parts.append("ORDER BY client_name")
            final_query = " ".join(query_parts)
            cursor.execute(final_query, tuple(params))
            rows = cursor.fetchall()
            client_names = [row[0] for row in rows]
        log.info(f"User {user_id}: Found {len(client_names)} unique client names with context '{data_context}'.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching unique client names: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"get_unique_client_names (user {user_id})")
    return client_names


def calculate_summary_by_client(user_id: str, start_date: Optional[dt.date] = None,
                                end_date: Optional[dt.date] = None, data_context: Optional[str] = None) -> Dict[str, Dict[str, Decimal]]:
    """Calculates financial summaries for each client, optionally filtered by date and data_context."""
    log.info(f"User {user_id}: Calculating summary by client. Period: {start_date} to {end_date}, Context: {data_context}")
    conn = get_db_connection()
    if not conn: return {}

    client_summary: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"total_revenue": Decimal(0), "total_direct_cost": Decimal(0), "net_from_client": Decimal(0)})

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query_parts = ["""
                SELECT
                    client_name,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as client_revenue,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as client_direct_cost
                FROM public.transactions
                WHERE user_id = %s AND client_name IS NOT NULL AND client_name <> ''
            """]
            params: List[Any] = [user_id]
            if start_date: query_parts.append("AND date >= %s"); params.append(start_date)
            if end_date: query_parts.append("AND date <= %s"); params.append(end_date)
            if data_context: query_parts.append("AND data_context = %s"); params.append(data_context)
            query_parts.append("GROUP BY client_name ORDER BY client_name")
            final_query = " ".join(query_parts)
            cursor.execute(final_query, tuple(params))
            rows = cursor.fetchall()

            for row in rows:
                client = row['client_name']
                revenue = row.get('client_revenue', Decimal(0)) or Decimal(0)
                cost = row.get('client_direct_cost', Decimal(0)) or Decimal(0)
                client_summary[client]["total_revenue"] = revenue
                client_summary[client]["total_direct_cost"] = cost # Stored as negative
                client_summary[client]["net_from_client"] = revenue + cost
        log.info(f"User {user_id}: Calculated summaries for {len(client_summary)} clients with context '{data_context}'.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error calculating summary by client: {e}", exc_info=True)
    except Exception as e: # Catch other potential errors
        log.error(f"User {user_id}: Unexpected error calculating summary by client: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"calculate_summary_by_client (user {user_id})")
    return dict(client_summary)


# --- Rule Management & Feedback Functions ---
def get_user_rules(user_id: str) -> Dict[str, str]:
    """Retrieves all categorization rules defined by a user."""
    conn = get_db_connection()
    if not conn: return {}
    rules = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT description_key, category FROM public.user_rules WHERE user_id = %s", (user_id,))
            rules = {row['description_key']: row['category'] for row in cursor.fetchall()}
        log.debug(f"User {user_id}: Fetched {len(rules)} user rules.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching user rules: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"get_user_rules for {user_id}")
    return rules


def save_user_rule(user_id: str, description_key: str, category: str):
    """Saves or updates a user-defined categorization rule."""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.user_rules (user_id, description_key, category, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, description_key)
                DO UPDATE SET category = EXCLUDED.category, updated_at = NOW()
            """, (user_id, description_key.lower().strip(), category))
            conn.commit()
            log.info(f"User {user_id}: Saved user rule '{description_key.lower().strip()}' -> '{category}'.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error saving user rule: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"save_user_rule for {user_id}")


def get_llm_rules(user_id: str) -> Dict[str, str]:
    """Retrieves all LLM-suggested categorization rules for a user."""
    conn = get_db_connection()
    if not conn: return {}
    rules = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT description_key, category FROM public.llm_rules WHERE user_id = %s", (user_id,))
            rules = {row['description_key']: row['category'] for row in cursor.fetchall()}
        log.debug(f"User {user_id}: Fetched {len(rules)} LLM rules.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching LLM rules: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"get_llm_rules for {user_id}")
    return rules


def save_llm_rule(user_id: str, description_key: str, category: str):
    """Saves or updates an LLM-suggested categorization rule."""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.llm_rules (user_id, description_key, category, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, description_key)
                DO UPDATE SET category = EXCLUDED.category, updated_at = NOW()
            """, (user_id, description_key.lower().strip(), category))
            conn.commit()
            log.info(f"User {user_id}: Saved LLM rule '{description_key.lower().strip()}' -> '{category}'.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error saving LLM rule: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"save_llm_rule for {user_id}")


def clear_llm_rules_for_user(user_id: str):
    """Deletes all LLM-suggested rules for a given user."""
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM public.llm_rules WHERE user_id = %s', (user_id,))
            conn.commit()
            log.info(f"User {user_id}: Cleared all LLM rules ({cursor.rowcount} rows affected).")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error clearing LLM rules: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"clear_llm_rules_for_user {user_id}")


def log_llm_failed_query(user_id: str, query_text: str, llm_response: Optional[str], reason: Optional[str]):
    """Logs a failed query attempt to the LLM."""
    timestamp = dt.datetime.now(dt.timezone.utc)
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.llm_failed_queries (user_id, timestamp, query, llm_response, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, timestamp, query_text, llm_response, reason))
            conn.commit()
        log.info(f"User {user_id}: Logged failed LLM query. Reason: {reason}")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error logging failed LLM query: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"log_llm_failed_query for {user_id}")


def log_llm_user_report(user_id: str, query_text: str, incorrect_response: str, user_comment: Optional[str]):
    """Logs user feedback about an incorrect LLM response."""
    timestamp = dt.datetime.now(dt.timezone.utc)
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.llm_user_reports (user_id, timestamp, query, incorrect_llm_response, user_comment)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, timestamp, query_text, incorrect_response, user_comment))
            conn.commit()
        log.info(f"User {user_id}: Logged LLM user report for query '{query_text[:50]}...'.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error logging LLM user report: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"log_llm_user_report for {user_id}")


def log_user_feedback(user_id: Optional[str], feedback_type: Optional[str], comment: str, contact_email: Optional[str]):
    """Logs general user feedback about the application."""
    timestamp = dt.datetime.now(dt.timezone.utc)
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.user_feedback (user_id, timestamp, feedback_type, comment, contact_email)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, timestamp, feedback_type, comment, contact_email))
            conn.commit()
        log.info(f"Logged user feedback. Type: {feedback_type}, User: {user_id if user_id else 'Anonymous'}.")
    except psycopg2.Error as e:
        log.error(f"DB error logging user feedback: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, f"log_user_feedback for user {user_id if user_id else 'Anonymous'}")


if __name__ == "__main__":
    log.info("database_supabase.py executed directly for testing or schema initialization.")
    # This will ensure tables and indexes are created/updated if run directly
    initialize_database()

    # Example Test Connection
    conn_test = get_db_connection()
    if conn_test:
        log.info("Test connection to Supabase PostgreSQL successful.")
        # You can add more specific test queries here if needed
        # Example: Test user profile creation/retrieval
        # test_user_uuid = "your_test_supabase_user_uuid" # Replace with an actual test user UUID from your Supabase Auth
        # test_email = "test@example.com"
        # if test_user_uuid != "your_test_supabase_user_uuid": # Ensure it's not the placeholder
        #     profile = create_user_profile(test_user_uuid, test_email, "test_user_cli")
        #     if profile:
        #         log.info(f"Test profile created/retrieved: ID={profile.id}, Email={profile.email}, Username={profile.username}")
        #         retrieved_profile = get_user_profile_by_id(test_user_uuid)
        #         if retrieved_profile:
        #             log.info(f"Retrieved test profile: ID={retrieved_profile.id}, Username={retrieved_profile.username}")
        #         else:
        #             log.error(f"Failed to retrieve test profile for {test_user_uuid}")
        #     else:
        #         log.error(f"Failed to create/retrieve test profile for {test_user_uuid}")
        close_db_connection(conn_test, "main_test_connection")
    else:
        log.error("Test connection to Supabase PostgreSQL FAILED.")
    log.info("Finished direct execution of database_supabase.py.")
