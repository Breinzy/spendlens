# database_supabase.py
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
import datetime as dt
from typing import List, Optional, Tuple, Dict, Any
import os

from config import settings

log = logging.getLogger('database_supabase')
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)


# --- Data Classes (User, Transaction as before) ---
class User:
    def __init__(self, id: str, email: str, username: Optional[str] = None):
        self.id = id
        self.email = email
        self.username = username if username else email

    @classmethod
    def from_db_row(cls, row: Dict) -> Optional['User']:
        if not row: return None
        return cls(id=str(row.get('id')), email=row.get('email'), username=row.get('username'))


class Transaction:
    def __init__(self, id: Optional[int], user_id: str, date: Optional[dt.date],
                 description: Optional[str], amount: Optional[Decimal], category: Optional[str],
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 created_at: Optional[dt.datetime] = None,
                 updated_at: Optional[dt.datetime] = None):
        self.id = id;
        self.user_id = user_id;
        self.date = date;
        self.description = description
        self.amount = amount;
        self.category = category;
        self.transaction_type = transaction_type
        self.source_account_type = source_account_type;
        self.source_filename = source_filename
        self.raw_description = raw_description if raw_description else description
        self.client_name = client_name;
        self.invoice_id = invoice_id;
        self.project_id = project_id
        self.payout_source = payout_source;
        self.transaction_origin = transaction_origin
        self.created_at = created_at;
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_db_row(cls, row: Dict) -> 'Transaction':
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
            created_at=row.get('created_at'), updated_at=row.get('updated_at')
        )


# --- Database Connection & Initialization (as before) ---
def get_db_connection() -> Optional[psycopg2.extensions.connection]:
    db_connection_string = settings.SUPABASE_DB_CONN_STRING or os.environ.get('SUPABASE_DB_CONN_STRING')
    if not db_connection_string:
        log.error("SUPABASE_DB_CONN_STRING is not set. Cannot connect to database.")
        return None
    try:
        conn = psycopg2.connect(db_connection_string)
        return conn
    except psycopg2.Error as e:
        log.error(f"Error connecting to Supabase PostgreSQL database: {e}", exc_info=True)
        return None


def close_db_connection(conn: Optional[psycopg2.extensions.connection], context: str = "general"):
    if conn:
        try:
            conn.close()
        except psycopg2.Error as e:
            log.error(f"Error closing PostgreSQL connection: {e}", exc_info=True)


def initialize_database():
    # (Schema creation logic as in previous version)
    log.info("Initializing database schema for PostgreSQL...")
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            log.error("Cannot initialize database: No database connection.")
            return
        with conn.cursor() as cursor:
            # User Profiles Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_profiles (
                    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
                    email VARCHAR(255) UNIQUE, username VARCHAR(100) UNIQUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')
            # Transactions Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.transactions (
                    id SERIAL PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    date DATE NOT NULL, description TEXT NOT NULL, amount DECIMAL(19, 4) NOT NULL,
                    category VARCHAR(100) NOT NULL DEFAULT 'Uncategorized',
                    transaction_type VARCHAR(50), source_account_type VARCHAR(50),
                    source_filename TEXT, raw_description TEXT, client_name VARCHAR(255),
                    invoice_id VARCHAR(100), project_id VARCHAR(100), payout_source VARCHAR(100),
                    transaction_origin VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')
            # User Rules Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_rules (
                    id SERIAL PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    description_key TEXT NOT NULL, category VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), 
                    UNIQUE(user_id, description_key)
                );''')
            # LLM Rules Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_rules (
                    id SERIAL PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    description_key TEXT NOT NULL, category VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, description_key)
                );''')
            # LLM Failed Queries Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_failed_queries (
                    id SERIAL PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ NOT NULL, query TEXT NOT NULL, llm_response TEXT, reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );''')
            # LLM User Reports Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.llm_user_reports (
                    id SERIAL PRIMARY KEY, user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ NOT NULL, query TEXT NOT NULL, incorrect_llm_response TEXT NOT NULL,
                    user_comment TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMPTZ DEFAULT NOW()
                );''')
            # User Feedback Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS public.user_feedback (
                    id SERIAL PRIMARY KEY, user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
                    timestamp TIMESTAMPTZ NOT NULL, feedback_type VARCHAR(50), comment TEXT NOT NULL,
                    contact_email VARCHAR(255), status TEXT DEFAULT 'pending', created_at TIMESTAMPTZ DEFAULT NOW()
                );''')
            # Indexes
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON public.transactions (user_id, date);')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_transactions_user_client ON public.transactions (user_id, client_name);')  # Index for client_name
            conn.commit()
            log.info("Database initialization/schema check for PostgreSQL complete.")
    except psycopg2.Error as e:
        log.error(f"PostgreSQL error during database initialization: {e}", exc_info=True)
        if conn: conn.rollback()
    except Exception as e:
        log.error(f"Unexpected error during database initialization: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, "initialize_database")


# --- User Profile Management (as before) ---
def get_user_profile_by_id(user_supabase_id: str) -> Optional[User]:
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, email, username FROM public.user_profiles WHERE id = %s", (user_supabase_id,))
            row = cursor.fetchone()
            return User.from_db_row(row) if row else None
    finally:
        close_db_connection(conn)


def create_user_profile(user_supabase_id: str, email: str, username: Optional[str] = None) -> Optional[User]:
    conn = get_db_connection()
    if not conn: return None
    effective_username = username if username else email.split('@')[0]
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "INSERT INTO public.user_profiles (id, email, username) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING RETURNING id, email, username;",
                (user_supabase_id, email, effective_username)
            )
            created_row = cursor.fetchone()
            conn.commit()
            if created_row: return User.from_db_row(created_row)
            return get_user_profile_by_id(user_supabase_id)
    finally:
        close_db_connection(conn)


# --- Transaction Management (as before, with new client-specific functions below) ---
def clear_transactions_for_user(user_id: str):
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM public.transactions WHERE user_id = %s', (user_id,))
            conn.commit()
    finally:
        close_db_connection(conn)


def save_transactions(user_id: str, transactions: List[Transaction]) -> int:
    # ... (implementation as in previous version) ...
    if not transactions: return 0
    conn = get_db_connection()
    if not conn: return 0
    saved_count = 0
    try:
        with conn.cursor() as cursor:
            sql = """INSERT INTO public.transactions (
                         user_id, date, description, amount, category, transaction_type,
                         source_account_type, source_filename, raw_description,
                         client_name, invoice_id, project_id, payout_source, transaction_origin
                     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data_to_save = []
            for t in transactions:
                if t.date is None or t.amount is None: continue
                data_to_save.append((
                    user_id, t.date, t.description, t.amount, t.category,
                    t.transaction_type, t.source_account_type, t.source_filename, t.raw_description,
                    t.client_name, t.invoice_id, t.project_id, t.payout_source, t.transaction_origin
                ))
            if not data_to_save: return 0
            psycopg2.extras.execute_batch(cursor, sql, data_to_save)
            saved_count = len(data_to_save)
            conn.commit()
    finally:
        close_db_connection(conn)
    return saved_count


def update_transaction_category(user_id: str, transaction_id: int, new_category: str) -> bool:
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute('''UPDATE public.transactions SET category = %s, updated_at = NOW()
                              WHERE id = %s AND user_id = %s''',
                           (new_category, transaction_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    finally:
        close_db_connection(conn)


def get_transaction_by_id_for_user(user_id: str, transaction_id: int) -> Optional[Transaction]:
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """SELECT id, user_id, date, description, amount, category, transaction_type,
                              source_account_type, source_filename, raw_description,
                              client_name, invoice_id, project_id, payout_source, transaction_origin,
                              created_at, updated_at
                       FROM public.transactions WHERE id = %s AND user_id = %s"""
            cursor.execute(query, (transaction_id, user_id))
            row = cursor.fetchone()
            return Transaction.from_db_row(row) if row else None
    finally:
        close_db_connection(conn)


def get_all_transactions(user_id: str, start_date: Optional[dt.date] = None,
                         end_date: Optional[dt.date] = None, category: Optional[str] = None,
                         transaction_origin: Optional[str] = None, client_name: Optional[str] = None) -> List[
    Transaction]:  # Added client_name
    log.info(
        f"User {user_id}: Getting transactions. Filters: Start={start_date}, End={end_date}, Cat={category}, Origin={transaction_origin}, Client={client_name}")
    conn = get_db_connection()
    if not conn: return []
    transactions_list: List[Transaction] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """SELECT id, user_id, date, description, amount, category, transaction_type,
                              source_account_type, source_filename, raw_description,
                              client_name, invoice_id, project_id, payout_source, transaction_origin,
                              created_at, updated_at
                       FROM public.transactions WHERE user_id = %s"""
            params: List[Any] = [user_id]
            if start_date: query += " AND date >= %s"; params.append(start_date)
            if end_date: query += " AND date <= %s"; params.append(end_date)
            if category: query += " AND category = %s"; params.append(category)
            if transaction_origin: query += " AND transaction_origin = %s"; params.append(transaction_origin)
            if client_name: query += " AND client_name = %s"; params.append(client_name)  # Filter by client_name
            query += " ORDER BY date DESC, created_at DESC, id DESC"
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            transactions_list = [Transaction.from_db_row(row) for row in rows]
    finally:
        close_db_connection(conn)
    return transactions_list


def calculate_total_for_period(user_id: str, start_date: dt.date, end_date: dt.date,
                               category: Optional[str] = None, exclude_categories: Optional[List[str]] = None,
                               transaction_type: Optional[str] = None,
                               transaction_origin: Optional[str] = None,
                               client_name: Optional[str] = None) -> Decimal:  # Added client_name
    log.info(
        f"User {user_id}: Calculating total. Period: {start_date}-{end_date}, Cat={category}, ExclCats={exclude_categories}, Type={transaction_type}, Origin={transaction_origin}, Client={client_name}")
    conn = get_db_connection()
    if not conn: return Decimal('0')
    total = Decimal('0')
    try:
        with conn.cursor() as cursor:
            query = "SELECT SUM(amount) FROM public.transactions WHERE user_id = %s AND date >= %s AND date <= %s"
            params: List[Any] = [user_id, start_date, end_date]
            if category: query += " AND category = %s"; params.append(category)
            if exclude_categories: query += " AND category NOT IN %s"; params.append(tuple(exclude_categories))
            if transaction_type == 'income':
                query += " AND amount > 0"
            elif transaction_type == 'spending':
                query += " AND amount < 0"
            if transaction_origin: query += " AND transaction_origin = %s"; params.append(transaction_origin)
            if client_name: query += " AND client_name = %s"; params.append(client_name)  # Filter by client_name
            cursor.execute(query, tuple(params))
            result = cursor.fetchone()
            if result and result[0] is not None: total = result[0]
    finally:
        close_db_connection(conn)
    return total


# --- New Client-Specific Functions ---
def get_unique_client_names(user_id: str, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None) -> \
List[str]:
    """Fetches a list of unique, non-null client names for a user within a date range."""
    log.info(f"User {user_id}: Fetching unique client names. Period: {start_date} to {end_date}")
    conn = get_db_connection()
    if not conn: return []
    client_names: List[str] = []
    try:
        with conn.cursor() as cursor:  # No RealDictCursor needed, just one column
            query = "SELECT DISTINCT client_name FROM public.transactions WHERE user_id = %s AND client_name IS NOT NULL AND client_name <> ''"
            params: List[Any] = [user_id]
            if start_date: query += " AND date >= %s"; params.append(start_date)
            if end_date: query += " AND date <= %s"; params.append(end_date)
            query += " ORDER BY client_name"
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            client_names = [row[0] for row in rows]
        log.info(f"User {user_id}: Found {len(client_names)} unique client names.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error fetching unique client names: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"get_unique_client_names (user {user_id})")
    return client_names


def calculate_summary_by_client(user_id: str, start_date: Optional[dt.date] = None,
                                end_date: Optional[dt.date] = None) -> Dict[str, Dict[str, Decimal]]:
    """
    Calculates financial summaries (total_revenue, total_expenses_linked_to_client) for each client.
    Returns a dictionary where keys are client names.
    'total_revenue' considers positive transactions where client_name is present.
    'total_direct_cost' considers negative transactions where client_name is present (e.g. refund to client, or cost directly tied to client work).
    """
    log.info(f"User {user_id}: Calculating summary by client. Period: {start_date} to {end_date}")
    conn = get_db_connection()
    if not conn: return {}

    client_summary: Dict[str, Dict[str, Decimal]] = defaultdict(
        lambda: {"total_revenue": Decimal(0), "total_direct_cost": Decimal(0)})

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT 
                    client_name, 
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as client_revenue,
                    SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as client_direct_cost 
                FROM public.transactions 
                WHERE user_id = %s AND client_name IS NOT NULL AND client_name <> ''
            """
            params: List[Any] = [user_id]
            if start_date: query += " AND date >= %s"; params.append(start_date)
            if end_date: query += " AND date <= %s"; params.append(end_date)
            query += " GROUP BY client_name ORDER BY client_name"

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            for row in rows:
                client = row['client_name']
                client_summary[client]["total_revenue"] = row.get('client_revenue', Decimal(0)) or Decimal(0)
                # client_direct_cost will be negative or zero, store as is.
                client_summary[client]["total_direct_cost"] = row.get('client_direct_cost', Decimal(0)) or Decimal(0)
                client_summary[client]["net_from_client"] = client_summary[client]["total_revenue"] + \
                                                            client_summary[client]["total_direct_cost"]

        log.info(f"User {user_id}: Calculated summaries for {len(client_summary)} clients.")
    except psycopg2.Error as e:
        log.error(f"User {user_id}: DB error calculating summary by client: {e}", exc_info=True)
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error calculating summary by client: {e}", exc_info=True)
    finally:
        close_db_connection(conn, f"calculate_summary_by_client (user {user_id})")
    return dict(client_summary)  # Convert defaultdict to dict


# --- Rule Management & Feedback Functions (as before) ---
def get_user_rules(user_id: str) -> Dict[str, str]:
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return {}
    rules = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT description_key, category FROM public.user_rules WHERE user_id = %s", (user_id,))
            rules = {row['description_key']: row['category'] for row in cursor.fetchall()}
    finally:
        close_db_connection(conn)
    return rules


def save_user_rule(user_id: str, description_key: str, category: str):
    # ... (implementation as in previous version) ...
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
    finally:
        close_db_connection(conn)


def get_llm_rules(user_id: str) -> Dict[str, str]:
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return {}
    rules = {}
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT description_key, category FROM public.llm_rules WHERE user_id = %s", (user_id,))
            rules = {row['description_key']: row['category'] for row in cursor.fetchall()}
    finally:
        close_db_connection(conn)
    return rules


def save_llm_rule(user_id: str, description_key: str, category: str):
    # ... (implementation as in previous version) ...
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
    finally:
        close_db_connection(conn)


def clear_llm_rules_for_user(user_id: str):
    # ... (implementation as in previous version) ...
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM public.llm_rules WHERE user_id = %s', (user_id,))
            conn.commit()
    finally:
        close_db_connection(conn)


def log_llm_failed_query(user_id: str, query_text: str, llm_response: Optional[str], reason: Optional[str]):
    # ... (implementation as in previous version) ...
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
    finally:
        close_db_connection(conn)


def log_llm_user_report(user_id: str, query_text: str, incorrect_response: str, user_comment: Optional[str]):
    # ... (implementation as in previous version) ...
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
    finally:
        close_db_connection(conn)


def log_user_feedback(user_id: Optional[str], feedback_type: Optional[str], comment: str, contact_email: Optional[str]):
    # ... (implementation as in previous version) ...
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
    finally:
        close_db_connection(conn)


if __name__ == "__main__":
    log.info("database_supabase.py executed directly for testing.")
    initialize_database()
    conn_test = get_db_connection()
    if conn_test:
        log.info("Test connection to Supabase PostgreSQL successful.")
        # Example: Test client breakdown functions
        # test_user_id_for_clients = "YOUR_TEST_SUPABASE_USER_UUID_WITH_CLIENT_DATA"
        # if test_user_id_for_clients != "YOUR_TEST_SUPABASE_USER_UUID_WITH_CLIENT_DATA":
        #     # Ensure some transactions with client_name exist for this user for testing
        #     clients = get_unique_client_names(test_user_id_for_clients)
        #     log.info(f"Test User's Unique Clients: {clients}")
        #     client_summaries = calculate_summary_by_client(test_user_id_for_clients)
        #     log.info(f"Test User's Client Summaries: {client_summaries}")
        #     for client, summary in client_summaries.items():
        #         print(f"Client: {client}, Revenue: {summary['total_revenue']}, Direct Cost: {summary['total_direct_cost']}, Net: {summary['net_from_client']}")

        close_db_connection(conn_test, "main_test_connection")
    else:
        log.error("Test connection to Supabase PostgreSQL FAILED.")
