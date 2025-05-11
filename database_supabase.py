# database_supabase.py
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from decimal import Decimal, InvalidOperation
import datetime as dt
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Tuple, Dict, Any
import os
from collections import defaultdict

from config import settings

log = logging.getLogger('database_supabase')
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)


class User:
    def __init__(self, id: str, email: str, username: Optional[str] = None):
        self.id = id
        self.email = email
        self.username = username if username else email.split('@')[0]

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
                 data_context: Optional[str] = 'business',
                 rate: Optional[Decimal] = None,
                 quantity: Optional[Decimal] = None,
                 invoice_status: Optional[str] = None,
                 date_paid: Optional[dt.date] = None,
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
        self.data_context = data_context
        self.rate = rate
        self.quantity = quantity
        self.invoice_status = invoice_status
        self.date_paid = date_paid
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        data = {
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
            "data_context": self.data_context,
            "rate": str(self.rate) if self.rate is not None else None,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "invoice_status": self.invoice_status,
            "date_paid": self.date_paid.isoformat() if self.date_paid else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return data

    @classmethod
    def from_db_row(cls, row: Dict) -> 'Transaction':
        def to_decimal(value: Any) -> Optional[Decimal]:
            if value is None: return None
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                log.warning(f"Could not convert value '{value}' to Decimal in from_db_row.")
                return None

        return cls(
            id=row.get('id'), user_id=str(row.get('user_id')), date=row.get('date'),
            description=row.get('description'), amount=to_decimal(row.get('amount')),
            category=row.get('category'), transaction_type=row.get('transaction_type'),
            source_account_type=row.get('source_account_type'),
            source_filename=row.get('source_filename'), raw_description=row.get('raw_description'),
            client_name=row.get('client_name'), invoice_id=row.get('invoice_id'),
            project_id=row.get('project_id'), payout_source=row.get('payout_source'),
            transaction_origin=row.get('transaction_origin'), data_context=row.get('data_context'),
            rate=to_decimal(row.get('rate')), quantity=to_decimal(row.get('quantity')),
            invoice_status=row.get('invoice_status'), date_paid=row.get('date_paid'),
            created_at=row.get('created_at'), updated_at=row.get('updated_at')
        )


def get_db_connection() -> Optional[psycopg2.extensions.connection]:
    db_connection_string = settings.SUPABASE_DB_CONN_STRING or os.environ.get('SUPABASE_DB_CONN_STRING')
    if not db_connection_string:
        log.error("SUPABASE_DB_CONN_STRING is not set.")
        return None
    try:
        conn = psycopg2.connect(db_connection_string)
        log.debug("Database connection successful.")
        return conn
    except psycopg2.Error as e:
        log.error(f"Error connecting to Supabase PostgreSQL: {e}", exc_info=True)
        return None


def close_db_connection(conn: Optional[psycopg2.extensions.connection], context: str = "general_operation"):
    if conn:
        try:
            conn.close()
            log.debug(f"Database connection closed for {context}.")
        except psycopg2.Error as e:
            log.error(f"Error closing PostgreSQL connection for {context}: {e}", exc_info=True)


def initialize_database():
    log.info("Initializing database schema for PostgreSQL...")
    # ... (ensure this function is complete and correct as per previous versions) ...
    # This function should define the 'transactions' table with all columns including:
    # rate, quantity, invoice_status, date_paid
    conn = get_db_connection()
    if not conn:
        log.error("Cannot initialize database: No database connection.")
        return
    try:
        with conn.cursor() as cursor:
            # User Profiles Table
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

            # Transactions Table - Ensure all columns are here
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
                    data_context VARCHAR(50) NOT NULL DEFAULT 'business',
                    rate DECIMAL(19, 4) NULL,
                    quantity DECIMAL(19, 4) NULL,
                    invoice_status VARCHAR(50) NULL,
                    date_paid DATE NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            ''')
            log.debug("Checked/Created transactions table with all columns.")
            # ... (rest of table creations: user_rules, llm_rules, etc.)
            conn.commit()
    except Exception as e:
        log.error(f"Error during database initialization: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        close_db_connection(conn, "initialize_database")


# --- User Profile Management ---
def get_user_profile_by_id(user_supabase_id: str) -> Optional[User]:
    conn = get_db_connection()
    if not conn: return None
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


# THIS IS THE FUNCTION IN QUESTION
def create_user_profile(user_supabase_id: str, email: str, username: Optional[str] = None) -> Optional[User]:
    """Creates a new user profile or returns existing if ID matches, ensuring email and username are updated if needed."""
    conn = get_db_connection()
    if not conn:
        log.error(f"Cannot create/update profile for {email}: No DB connection.")
        return None

    effective_username = username if username else email.split('@')[0]
    log.info(
        f"Attempting to create/update profile for Supabase ID: {user_supabase_id}, Email: {email}, Username: {effective_username}")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Upsert logic: Insert if not exists, otherwise update email and username if they are different
            # and preserve existing username if the new one is None but an old one exists.
            cursor.execute(
                """
                INSERT INTO public.user_profiles (id, email, username, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    username = COALESCE(public.user_profiles.username, EXCLUDED.username), 
                    updated_at = NOW()
                WHERE public.user_profiles.email IS DISTINCT FROM EXCLUDED.email
                   OR public.user_profiles.username IS DISTINCT FROM EXCLUDED.username 
                   OR public.user_profiles.username IS NULL AND EXCLUDED.username IS NOT NULL 
                RETURNING id, email, username, created_at, updated_at;
                """,
                (user_supabase_id, email, effective_username)
            )
            profile_row = cursor.fetchone()
            conn.commit()

            if profile_row:
                log.info(
                    f"Profile successfully created/updated for Supabase ID {user_supabase_id}. Email: {profile_row.get('email')}, Username: {profile_row.get('username')}")
                return User.from_db_row(profile_row)
            else:
                # If RETURNING didn't yield a row (e.g., because nothing changed and WHERE clause of DO UPDATE was false)
                # It means the profile likely exists and is up-to-date. Fetch it to be sure.
                log.info(
                    f"Profile for Supabase ID {user_supabase_id} likely exists and is up-to-date. Fetching to confirm.")
                return get_user_profile_by_id(user_supabase_id)

    except psycopg2.Error as e:
        log.error(f"DB error during profile upsert for Supabase ID {user_supabase_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    except Exception as e:
        log.error(f"Unexpected error during profile upsert for Supabase ID {user_supabase_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        close_db_connection(conn, f"create_user_profile for {user_supabase_id}")


# ... (rest of the file: save_transactions, get_all_transactions, monthly revenue functions, etc.)
# Ensure all other functions are present and correct as per previous versions.
# The following are stubs for brevity but should be fully implemented in your file.

def save_transactions(user_id: str, transactions: List[Transaction]) -> int:
    # ... (full implementation) ...
    log.info(f"User {user_id}: Saved X transactions.")
    return 0


def get_all_transactions(user_id: str, start_date: Optional[dt.date] = None,
                         end_date: Optional[dt.date] = None, category: Optional[str] = None,
                         transaction_origin: Optional[str] = None, client_name: Optional[str] = None,
                         data_context: Optional[str] = None,
                         project_id: Optional[str] = None
                         ) -> List[Transaction]:
    # ... (full implementation) ...
    log.info(f"User {user_id}: Fetched X transactions.")
    return []


def get_revenue_for_past_n_months(user_id: str, num_months: int, data_context: Optional[str] = 'business') -> Dict[
    str, Decimal]:
    # ... (full implementation) ...
    return {}


def get_revenue_current_month_to_date(user_id: str, data_context: Optional[str] = 'business') -> Decimal:
    # ... (full implementation) ...
    return Decimal('0')


# ... (other functions like update_transaction_category, rule management, etc.)

if __name__ == "__main__":
    log.info("database_supabase.py executed directly.")
    initialize_database()
    log.info("Finished direct execution of database_supabase.py.")

