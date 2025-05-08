# parser.py
import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from dateutil.parser import parse as dateutil_parse, ParserError as DateParserError
from typing import List, Dict, Optional, Any, Union, TextIO, Set  # Added Set
import io

# --- Constants ---
DUMMY_CLI_USER_ID = "cli_report_user"  # For CLI report generator if used without a real user

# --- Database Interaction (with fallback for standalone testing) ---
try:
    import database_supabase as database  # Main import for application use

    log_parser_db_status = "database_supabase imported successfully."
except ModuleNotFoundError:
    # This block is for standalone testing of parser.py or CLI use
    # It defines a DummyDB to avoid errors if database_supabase is not found.
    class DummyDB:
        """A dummy database interface for standalone parser testing."""

        def __init__(self):
            self._log = logging.getLogger('parser_dummy_db')
            self._log.warning("Using DummyDB for parser.py. No actual database operations will occur.")

        def get_user_rules(self, user_id: str) -> Dict[str, str]:
            self._log.debug(f"DummyDB: get_user_rules called for {user_id}")
            return {}

        def get_llm_rules(self, user_id: str) -> Dict[str, str]:
            self._log.debug(f"DummyDB: get_llm_rules called for {user_id}")
            return {}

        def save_user_rule(self, user_id: str, key: str, cat: str):
            self._log.debug(f"DummyDB: save_user_rule for {user_id}: '{key}' -> '{cat}'")

        def save_llm_rule(self, user_id: str, key: str, cat: str):
            self._log.debug(f"DummyDB: save_llm_rule for {user_id}: '{key}' -> '{cat}'")


    database = DummyDB()
    log_parser_db_status = "Failed to import 'database_supabase'. Using DummyDB."

# --- Logging Setup ---
log = logging.getLogger('parser')  # Main logger for the parser module
# Configure based on a global setting if available, else default to INFO
# from config import settings # Assuming settings.DEBUG_MODE exists
# log.setLevel(logging.DEBUG if settings.DEBUG_MODE else logging.INFO)
log.setLevel(logging.INFO)  # Default, can be overridden by app config

if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
log.info(f"Parser module initialized. DB status: {log_parser_db_status}")

# --- Global Vendor Rules ---
VENDOR_RULES_FILE = 'vendors.json'  # Predefined rules for common vendors
VENDOR_RULES: Dict[str, str] = {}  # Loaded at module level


# --- Transaction Data Class ---
class Transaction:
    """Represents a financial transaction, mirroring database_supabase.Transaction."""

    def __init__(self, id: Optional[int] = None, user_id: str = "", date: Optional[dt.date] = None,
                 description: Optional[str] = None, amount: Optional[Decimal] = None, category: Optional[str] = None,
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 data_context: Optional[str] = 'business',  # NEW: Default to 'business'
                 rate: Optional[Decimal] = None, quantity: Optional[Decimal] = None,
                 invoice_status: Optional[str] = None, date_paid: Optional[dt.date] = None,
                 created_at: Optional[dt.datetime] = None, updated_at: Optional[dt.datetime] = None):
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
        self.project_id = project_id  # This can be overridden by file-level or column-level data
        self.payout_source = payout_source
        self.transaction_origin = transaction_origin
        self.data_context = data_context  # Assign the context
        self.rate = rate
        self.quantity = quantity
        self.invoice_status = invoice_status
        self.date_paid = date_paid
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        """Converts Transaction to a dictionary for serialization."""
        return {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if v is not None}


# --- Utility Functions ---
def allowed_file(filename: str, allowed_extensions: Optional[Set[str]] = None) -> bool:
    """Checks if the file has an allowed extension."""
    if allowed_extensions is None:
        allowed_extensions = {'csv'}  # Default if not provided by settings
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def load_vendor_rules(filepath: str) -> Dict[str, str]:
    """Loads vendor categorization rules from a JSON file."""
    rules: Dict[str, str] = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():  # Handle empty file
                    log.info(f"Vendor rules file '{filepath}' is empty.")
                    return {}
                rules = json.loads(content)
            log.info(f"Loaded {len(rules)} vendor rules from '{filepath}'.")
            return {k.lower().strip(): v for k, v in rules.items()}  # Normalize keys
        except json.JSONDecodeError as jde:
            log.error(f"Error decoding JSON from vendor rules file '{filepath}': {jde}", exc_info=True)
        except Exception as e:
            log.error(f"Error loading vendor rules from '{filepath}': {e}", exc_info=True)
    else:
        log.warning(f"Vendor rules file not found: '{filepath}'. No vendor rules loaded.")
    return {}


VENDOR_RULES = load_vendor_rules(VENDOR_RULES_FILE)  # Load on module import


def add_user_rule(user_id: str, description_fragment: str, category: str):
    """Saves a user-defined categorization rule to the database."""
    if user_id == DUMMY_CLI_USER_ID:  # Special case for CLI tool
        log.info(f"CLI mode: Skipping save_user_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category:
        log.warning(f"User {user_id}: Attempt to save empty user rule or category.")
        return
    try:
        database.save_user_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:  # Catch potential DB errors
        log.error(f"Failed to save user rule for user {user_id} ('{description_fragment}' -> '{category}'): {e}",
                  exc_info=True)


def save_llm_rule(user_id: str, description_fragment: str, category: str):
    """Saves an LLM-suggested categorization rule to the database."""
    if user_id == DUMMY_CLI_USER_ID:
        log.info(f"CLI mode: Skipping save_llm_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category:
        log.warning(f"User {user_id}: Attempt to save empty LLM rule or category.")
        return
    try:
        database.save_llm_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save LLM rule for user {user_id} ('{description_fragment}' -> '{category}'): {e}",
                  exc_info=True)


def categorize_transaction(user_id: str, description: str) -> str:
    """Categorizes a transaction based on user, vendor, and LLM rules."""
    if not description:
        return 'Uncategorized'
    desc_lower = description.lower().strip()

    # Priority: User rules, Vendor rules, LLM rules
    if user_id != DUMMY_CLI_USER_ID:  # Skip DB calls for CLI dummy user
        user_rules = database.get_user_rules(user_id)
        for key in sorted(user_rules.keys(), key=len, reverse=True):  # Longer keys first
            if key in desc_lower:
                log.debug(f"User {user_id}: User rule match for '{description}' ('{key}' -> '{user_rules[key]}')")
                return user_rules[key]

    for key in sorted(VENDOR_RULES.keys(), key=len, reverse=True):
        if key in desc_lower:
            log.debug(f"User {user_id}: Vendor rule match for '{description}' ('{key}' -> '{VENDOR_RULES[key]}')")
            return VENDOR_RULES[key]

    if user_id != DUMMY_CLI_USER_ID:
        llm_rules = database.get_llm_rules(user_id)
        for key in sorted(llm_rules.keys(), key=len, reverse=True):
            if key in desc_lower:
                log.debug(f"User {user_id}: LLM rule match for '{description}' ('{key}' -> '{llm_rules[key]}')")
                return llm_rules[key]

    log.debug(f"User {user_id}: No rule match for '{description}'. Defaulting to Uncategorized.")
    return 'Uncategorized'


def _get_text_stream(user_id: str, file_like_object: Union[io.BytesIO, TextIO], filename: str,
                     parser_name: str) -> TextIO:
    """Converts BytesIO to TextIO or validates TextIO, handling common encodings."""
    if isinstance(file_like_object, io.BytesIO):
        try:
            # Try UTF-8 with BOM first, then plain UTF-8
            return io.TextIOWrapper(file_like_object, encoding='utf-8-sig', errors='replace')
        except UnicodeDecodeError:
            log.warning(f"User {user_id}: UTF-8 decoding failed for '{filename}' in {parser_name}. Trying latin-1.")
            file_like_object.seek(0)  # Reset stream position before trying another encoding
            return io.TextIOWrapper(file_like_object, encoding='latin-1', errors='replace')
    # Check if it's already a text stream (like TextIOWrapper or an opened text file)
    elif isinstance(file_like_object, io.TextIOBase):
        return file_like_object
    else:  # Should not happen if input is UploadFile.file or BytesIO
        log.error(
            f"User {user_id}: Invalid file object type '{type(file_like_object)}' for '{filename}' in {parser_name}.")
        raise TypeError(f"{parser_name} expects a BytesIO or TextIOBase object, got {type(file_like_object)}.")


def parse_csv_with_schema(
        user_id: str,
        file_stream: TextIO,  # Expects a text stream (e.g., from _get_text_stream)
        schema: Dict[str, Any],
        transaction_origin: str,
        source_filename: str,
        account_type: Optional[str] = None,
        data_context_override: Optional[str] = "business",  # NEW: For file-level context
        project_id_override: Optional[str] = None  # NEW: For file-level project ID
) -> List[Transaction]:
    """
    Generic CSV parser using a schema to map columns to Transaction fields.
    Now includes data_context and project_id handling.
    """
    transactions: List[Transaction] = []
    log.info(
        f"User {user_id}: Schema parsing. Origin:'{transaction_origin}', File:'{source_filename}', Context:'{data_context_override}', Project:'{project_id_override}'")

    try:
        # Skip initial lines if specified in schema (e.g., for headers above the actual header row)
        skip_lines = schema.get("skip_initial_lines", 0)
        for _ in range(skip_lines):
            next(file_stream)

        reader = csv.DictReader(file_stream)
        if not reader.fieldnames:
            raise ValueError(f"CSV file '{source_filename}' appears to be empty or headerless after skipping lines.")

        # Normalize CSV headers for robust mapping (lowercase, strip whitespace)
        csv_headers_map = {name.lower().strip(): name for name in reader.fieldnames}
        log.debug(f"User {user_id}: CSV Headers for '{source_filename}': {reader.fieldnames}")
        log.debug(f"User {user_id}: Normalized CSV Headers Map: {csv_headers_map}")

        def get_actual_col_name(schema_field_keys: List[str]) -> Optional[str]:
            """Finds the actual column name from CSV given a list of possible schema keys."""
            for key_option in schema_field_keys:
                normalized_key = key_option.lower().strip()
                if normalized_key in csv_headers_map:
                    return csv_headers_map[normalized_key]  # Return original case from CSV
            return None

        # Map schema fields to actual column names from the CSV
        date_col = get_actual_col_name(schema.get("date_fields", []))
        desc_col = get_actual_col_name(schema.get("description_fields", []))
        amount_col = get_actual_col_name(schema.get("amount_fields", []))
        # ... (other column mappings as before)
        rate_col = get_actual_col_name(schema.get("rate_fields", []))
        quantity_col = get_actual_col_name(schema.get("quantity_fields", []))
        invoice_status_col = get_actual_col_name(schema.get("invoice_status_fields", []))
        date_paid_col = get_actual_col_name(schema.get("date_paid_fields", []))
        type_col = get_actual_col_name(schema.get("transaction_type_fields", []))
        category_col_csv = get_actual_col_name(schema.get("category_fields", []))  # Category from CSV
        client_name_col = get_actual_col_name(schema.get("client_name_fields", []))
        invoice_id_col = get_actual_col_name(schema.get("invoice_id_fields", []))
        project_id_col_csv = get_actual_col_name(schema.get("project_id_fields", []))  # Project ID from CSV
        payout_source_col_name = get_actual_col_name(schema.get("payout_source_fields", []))
        duration_col = get_actual_col_name(schema.get("duration_fields", []))  # For time logs
        billable_rate_col = get_actual_col_name(schema.get("billable_rate_fields", []))  # For time logs

        # Validate essential columns are found
        required_map = {"Date": date_col, "Description": desc_col}  # Amount is handled specially for time logs
        if transaction_origin not in ['clockify_log',
                                      'toggl_log'] and not amount_col:  # Amount is required for non-time logs
            required_map["Amount"] = amount_col
        elif transaction_origin in ['clockify_log', 'toggl_log'] and not amount_col and not (
                duration_col and billable_rate_col):
            raise ValueError(
                f"For time log '{source_filename}', Amount column is missing, AND 'Duration' or 'Billable Rate' columns are also missing. Cannot calculate amount.")

        missing_essentials = [k for k, v in required_map.items() if not v]
        if missing_essentials:
            raise ValueError(
                f"Missing essential columns in '{source_filename}' based on schema '{transaction_origin}': {', '.join(missing_essentials)}. Available headers: {list(csv_headers_map.keys())}")

        date_format_hint = schema.get("date_format")  # Date format string from schema

        for i, row_dict in enumerate(reader):
            row_num = i + 2 + skip_lines  # Adjust row number for logging if lines were skipped
            try:
                date_str = row_dict.get(date_col) if date_col else None
                raw_desc_val = row_dict.get(desc_col, '') if desc_col else ''

                if not date_str or not raw_desc_val.strip():  # Skip if no date or description is effectively empty
                    log.warning(
                        f"Row {row_num}: Skipping due to missing date or empty description. File: {source_filename}")
                    continue
                description = ' '.join(raw_desc_val.strip().split())  # Normalize whitespace

                transaction_date: Optional[dt.date] = None
                try:
                    if date_format_hint:
                        transaction_date = dt.datetime.strptime(date_str.strip(), date_format_hint).date()
                    else:  # Flexible parsing if no format hint
                        transaction_date = dateutil_parse(date_str.strip()).date()
                except (DateParserError, ValueError, TypeError) as e:
                    log.warning(
                        f"Row {row_num}: Skipping due to unparseable date '{date_str}': {e}. File: {source_filename}")
                    continue

                # --- Amount Processing ---
                amount_val = Decimal('0')
                amount_str = row_dict.get(amount_col) if amount_col else None
                if amount_str:
                    try:
                        cleaned_amount_str = str(amount_str).replace('$', '').replace(',', '').strip()
                        if cleaned_amount_str.startswith('(') and cleaned_amount_str.endswith(
                                ')'):  # Handle (123.45) for negative
                            cleaned_amount_str = '-' + cleaned_amount_str[1:-1]
                        amount_val = Decimal(cleaned_amount_str)
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid amount '{amount_str}', using 0. File: {source_filename}")
                # Special handling for time logs if amount is zero or not present
                elif transaction_origin in ['clockify_log', 'toggl_log'] and duration_col and billable_rate_col:
                    duration_str_tl = row_dict.get(duration_col)
                    billable_rate_str_tl = row_dict.get(billable_rate_col)
                    if duration_str_tl and billable_rate_str_tl:
                        try:
                            # Attempt to parse duration (e.g., "1:30:00" or "1.5")
                            duration_decimal_hours = Decimal('0')
                            if ':' in duration_str_tl:  # HH:MM:SS or MM:SS format
                                parts = duration_str_tl.split(':')
                                if len(parts) == 3:  # HH:MM:SS
                                    duration_decimal_hours = Decimal(parts[0]) + (Decimal(parts[1]) / 60) + (
                                                Decimal(parts[2]) / 3600)
                                elif len(parts) == 2:  # MM:SS (treat as hours:minutes for simplicity, or adjust schema)
                                    duration_decimal_hours = Decimal(parts[0]) + (Decimal(parts[1]) / 60)
                            else:  # Assume decimal hours
                                duration_decimal_hours = Decimal(duration_str_tl)

                            rate_decimal_tl = Decimal(
                                str(billable_rate_str_tl).replace('$', '').replace(',', '').strip())
                            amount_val = duration_decimal_hours * rate_decimal_tl
                            log.debug(
                                f"Row {row_num}: Calculated amount {amount_val} from duration {duration_decimal_hours} and rate {rate_decimal_tl} for time log.")
                        except (InvalidOperation, ValueError, TypeError) as time_calc_err:
                            log.warning(
                                f"Row {row_num}: Could not calculate amount from time log. Duration: '{duration_str_tl}', Rate: '{billable_rate_str_tl}'. Error: {time_calc_err}. File: {source_filename}")

                # Skip zero-amount transactions unless allowed by schema (e.g., non-billable time logs)
                if amount_val == Decimal('0') and not schema.get("allow_zero_amount_transactions", False):
                    is_billable_col_name = get_actual_col_name(schema.get("is_billable_fields", []))
                    is_billable_str = row_dict.get(is_billable_col_name,
                                                   "yes").lower() if is_billable_col_name and row_dict.get(
                        is_billable_col_name) else "yes"

                    if transaction_origin in ['clockify_log', 'toggl_log'] and is_billable_str in ['no', 'false', '0',
                                                                                                   'non-billable',
                                                                                                   'non billable']:
                        log.debug(
                            f"Row {row_num}: Skipping non-billable zero-amount time entry. File: {source_filename}")
                        continue
                    elif transaction_origin not in ['clockify_log', 'toggl_log']:  # For other types, skip if zero
                        log.debug(f"Row {row_num}: Skipping zero-amount transaction. File: {source_filename}")
                        continue
                    # If it's a billable time log but amount is still zero, it might be an issue or free work. Let it pass if allow_zero_amount_transactions is true.

                # --- Other Fields ---
                tx_type_csv = row_dict.get(type_col, "").strip() if type_col else None
                tx_type = tx_type_csv if tx_type_csv else ('CREDIT' if amount_val > 0 else 'DEBIT')

                category_from_csv = row_dict.get(category_col_csv, "").strip() if category_col_csv else None
                category = category_from_csv if category_from_csv and category_from_csv.lower() != 'uncategorized' else categorize_transaction(
                    user_id, description)
                if transaction_origin in ['clockify_log',
                                          'toggl_log'] and category.lower() == 'uncategorized' and amount_val != Decimal(
                        '0'):
                    category = "Time Tracking Revenue"  # Default for billable time logs

                client_name = row_dict.get(client_name_col, "").strip() if client_name_col else None
                invoice_id = row_dict.get(invoice_id_col, "").strip() if invoice_id_col else None
                payout_source_val = row_dict.get(payout_source_col_name, "").strip() if payout_source_col_name else None

                # Project ID: CSV column takes precedence over file-level override
                project_id_from_csv = row_dict.get(project_id_col_csv, "").strip() if project_id_col_csv else None
                final_project_id = project_id_from_csv if project_id_from_csv else project_id_override

                # Rate and Quantity
                rate_val: Optional[Decimal] = None
                if rate_col and row_dict.get(rate_col):
                    try:
                        rate_val = Decimal(str(row_dict[rate_col]).replace('$', '').replace(',', '').strip())
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid rate '{row_dict[rate_col]}'.")
                quantity_val: Optional[Decimal] = None
                if quantity_col and row_dict.get(quantity_col):
                    try:
                        quantity_val = Decimal(str(row_dict[quantity_col]).strip())
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid quantity '{row_dict[quantity_col]}'.")

                # Invoice Status and Date Paid
                invoice_status_str = row_dict.get(invoice_status_col,
                                                  "").strip().lower() if invoice_status_col else None
                date_paid_val: Optional[dt.date] = None
                if date_paid_col and row_dict.get(date_paid_col):
                    try:
                        date_paid_val = dateutil_parse(row_dict[date_paid_col].strip()).date()
                    except (DateParserError, ValueError, TypeError):
                        log.warning(f"Row {row_num}: Unparseable Date Paid '{row_dict[date_paid_col]}'.")

                transactions.append(Transaction(
                    user_id=user_id, date=transaction_date, description=description, amount=amount_val,
                    category=category, transaction_type=tx_type, source_account_type=account_type,
                    source_filename=source_filename, raw_description=raw_desc_val.strip(),
                    client_name=client_name, invoice_id=invoice_id, project_id=final_project_id,  # Use final_project_id
                    payout_source=payout_source_val, transaction_origin=transaction_origin,
                    data_context=data_context_override,  # Assign file-level context
                    rate=rate_val, quantity=quantity_val,
                    invoice_status=invoice_status_str, date_paid=date_paid_val
                ))
            except Exception as row_err:  # Catch errors within row processing loop
                log.error(f"Row {row_num}: Error processing. File: '{source_filename}'. Error: {row_err}",
                          exc_info=False)  # Set exc_info=False for less verbose logs per row
                # Optionally, collect these errors to return to the user
        log.info(f"User {user_id}: Successfully parsed '{source_filename}'. Found {len(transactions)} transactions.")
        return transactions
    except ValueError as ve:  # Errors like missing essential columns
        log.error(f"User {user_id}: Value error parsing CSV '{source_filename}': {ve}",
                  exc_info=True)  # Show full traceback for these
        raise  # Re-raise to be caught by the router
    except Exception as e:  # Other unexpected errors during setup or reading
        log.error(f"User {user_id}: Unexpected critical error parsing '{source_filename}': {e}", exc_info=True)
        raise RuntimeError(f"Failed to parse {source_filename} due to an unexpected error.") from e


# --- Specific Parser Functions ---
# Each specific parser function now needs to accept data_context_override and project_id_override
# and pass them to parse_csv_with_schema.

CHASE_COMMON_SCHEMA = {
    "date_fields": ["Transaction Date", "Posting Date"],
    "description_fields": ["Description"],
    "amount_fields": ["Amount"],
    "transaction_type_fields": ["Type"],  # e.g., SALE, PAYMENT, FEE
    "category_fields": ["Category"],  # Chase sometimes provides a category
    "date_format": "%m/%d/%Y"  # Common Chase format
}


def parse_checking_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                       data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_checking_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_checking', filename, 'checking',
                                 data_context_override, project_id_override)


def parse_credit_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_credit_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_credit', filename, 'credit',
                                 data_context_override, project_id_override)


STRIPE_PAYOUTS_SCHEMA = {
    "date_fields": ["created", "created_utc", "available_on", "available_on_utc", "date", "Arrival Date"],
    "description_fields": ["description", "summary", "charge id", "payment intent id", "Description", "Source"],
    "amount_fields": ["net", "amount", "Net", "Amount"],  # Case variations
    "transaction_type_fields": ["type", "Type"],
    "invoice_id_fields": ["charge_id", "payment_intent_id", "source_id", "invoice", "id", "Charge ID"],
    "payout_source_fields": ["source_type", "card_brand", "Network"],
    "client_name_fields": ["customer_facing_descriptor", "customer_email", "customer_name", "metadata.client_name",
                           "Customer Name", "Customer Email"],
    "date_format": None,  # Stripe uses ISO 8601 or Unix timestamps, dateutil handles them
}


def parse_stripe_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_stripe_csv")
    return parse_csv_with_schema(user_id, s, STRIPE_PAYOUTS_SCHEMA, 'stripe_transaction', filename, None,
                                 data_context_override, project_id_override)


PAYPAL_TRANSACTIONS_SCHEMA = {
    "date_fields": ["Date"],
    "description_fields": ["Name", "Item Title", "Subject", "Note", "Type"],  # 'Type' can also be part of description
    "amount_fields": ["Net", "Gross"],  # Prefer Net if available
    "transaction_type_fields": ["Type"],  # PayPal's 'Type' column
    "invoice_id_fields": ["Invoice Number", "Transaction ID"],
    "client_name_fields": ["Name", "From Email Address"],  # 'Name' is often the counterparty
    "date_format": "%m/%d/%Y"  # Common PayPal format
}


def parse_paypal_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                     data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_paypal_csv")
    return parse_csv_with_schema(user_id, s, PAYPAL_TRANSACTIONS_SCHEMA, 'paypal_transaction', filename, None,
                                 data_context_override, project_id_override)


GENERIC_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Invoice Date", "Payment Date", "Date"],
    "description_fields": ["Item Description", "Item Name", "Description", "Line Item Description", "Service Rendered",
                           "Memo"],
    "amount_fields": ["Line Total", "Total Amount", "Amount Paid", "Net Amount", "Total", "Amount"],
    "rate_fields": ["Rate", "Unit Price", "Price"],
    "quantity_fields": ["Quantity", "Qty", "Hours"],
    "client_name_fields": ["Client Name", "Customer", "Vendor Name", "Billed To", "Client"],
    "invoice_id_fields": ["Invoice #", "Invoice ID", "Reference Number", "Number", "Invoice Number"],
    "project_id_fields": ["Project Name", "Project Code", "Job", "Project"],
    "transaction_type_fields": ["Type", "Transaction Type"],
    "invoice_status_fields": ["Invoice Status", "Status"],
    "date_paid_fields": ["Date Paid", "Payment Date"],
    "date_format": None  # Allow flexible date parsing
}


def parse_invoice_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                      data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_invoice_csv")
    return parse_csv_with_schema(user_id, s, GENERIC_INVOICE_SCHEMA, 'invoice_import', filename, None,
                                 data_context_override, project_id_override)


FRESHBOOKS_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Date"],
    "description_fields": ["Item Description", "Item Name", "Description"],
    "amount_fields": ["Line Total", "Amount"],
    "rate_fields": ["Rate"],
    "quantity_fields": ["Quantity"],
    "client_name_fields": ["Client Name", "Client"],
    "invoice_id_fields": ["Invoice #", "Invoice Number"],
    "project_id_fields": ["Project Name", "Project"],
    "invoice_status_fields": ["Invoice Status", "Status"],
    "date_paid_fields": ["Date Paid"],
    "date_format": "%Y-%m-%d",  # Common FreshBooks export format
    "allow_zero_amount_transactions": True  # FreshBooks might have $0 lines for discounts etc.
}


def parse_freshbooks_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                         data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing FreshBooks CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_freshbooks_csv")
    return parse_csv_with_schema(user_id, text_stream, FRESHBOOKS_INVOICE_SCHEMA,
                                 transaction_origin='freshbooks_invoice',
                                 source_filename=filename,
                                 account_type=None,  # Not typically an account type
                                 data_context_override=data_context_override,
                                 project_id_override=project_id_override)


CLOCKIFY_SCHEMA = {
    "date_fields": ["Start Date", "Date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Billable Amount (USD)", "Billable Amount"],  # Let calculation happen if these are zero/missing
    "billable_rate_fields": ["Billable Rate (USD)", "Billable Rate"],  # Used for calculation
    "duration_fields": ["Duration (decimal)", "Duration (h)"],  # Used for calculation
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "is_billable_fields": ["Billable"],  # To identify non-billable zero-amount entries
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": True
    # Allow non-billable time to be parsed if needed, though usually skipped if amount is 0
}


def parse_clockify_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                       data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing Clockify CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_clockify_csv")
    return parse_csv_with_schema(user_id, text_stream, CLOCKIFY_SCHEMA,
                                 transaction_origin='clockify_log',
                                 source_filename=filename,
                                 data_context_override=data_context_override,
                                 project_id_override=project_id_override)


TOGGL_SCHEMA = {
    "date_fields": ["Start date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Amount (USD)", "Amount"],  # Let calculation happen
    "billable_rate_fields": ["Rate (USD)", "Rate"],  # Used for calculation
    "duration_fields": ["Duration"],  # Used for calculation (e.g., "01:30:00")
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "is_billable_fields": ["Billable"],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": True
}


def parse_toggl_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str,
                    data_context_override: str = "business", project_id_override: Optional[str] = None) -> List[
    Transaction]:
    log.info(
        f"User {user_id}: Parsing Toggl CSV '{filename}'. Context: {data_context_override}, Project: {project_id_override}")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_toggl_csv")
    return parse_csv_with_schema(user_id, text_stream, TOGGL_SCHEMA,
                                 transaction_origin='toggl_log',
                                 source_filename=filename,
                                 data_context_override=data_context_override,
                                 project_id_override=project_id_override)


if __name__ == '__main__':
    # This block is for direct testing of the parser module
    log.info("parser.py executed directly for testing.")
    test_user_id_cli = DUMMY_CLI_USER_ID  # Use the dummy ID for CLI tests

    # Create a dummy test file path
    test_files_dir = "temp_parser_test_files"
    os.makedirs(test_files_dir, exist_ok=True)

    # Test FreshBooks with data_context and project_id
    dummy_freshbooks_content = (
        "Client Name,Invoice #,Date Issued,Invoice Status,Date Paid,Item Name,Item Description,Rate,Quantity,Line Total,Currency,Project\n"
        "Client Alpha,INV-001,2025-05-01,paid,2025-05-10,Web Design,Homepage Mockup,75.00,10.0,750.00,USD,Website Revamp\n"
        "Client Beta,INV-002,2025-05-03,sent,,Consulting,Strategy Session,150.00,2.0,300.00,USD,Marketing Plan\n"
    )
    fb_filename = os.path.join(test_files_dir, "test_freshbooks_cli.csv")
    with open(fb_filename, 'w', encoding='utf-8') as f:
        f.write(dummy_freshbooks_content)

    print(f"\n--- Testing FreshBooks CSV Parser (CLI context) ---")
    with open(fb_filename, 'rb') as fb_file_obj:  # Open in binary for BytesIO
        freshbooks_bytes_io = io.BytesIO(fb_file_obj.read())
    try:
        # Simulate calling from router with overrides
        freshbooks_transactions = parse_freshbooks_csv(
            user_id=test_user_id_cli,
            file_obj=freshbooks_bytes_io,
            filename="test_freshbooks_cli.csv",
            data_context_override="business_test_override",  # Test override
            project_id_override="FILE_LEVEL_PROJECT_X"  # Test file-level project ID
        )
        for tx in freshbooks_transactions:
            print(f"Parsed FreshBooks Tx: Client: {tx.client_name}, Amount: {tx.amount}, "
                  f"Status: {tx.invoice_status}, Date Paid: {tx.date_paid}, Desc: {tx.description}, "
                  f"Context: {tx.data_context}, Project: {tx.project_id}")  # Check context and project
    except Exception as e_cli:
        print(f"Error parsing FreshBooks test CSV (CLI): {e_cli}", exc_info=True)
    finally:
        if os.path.exists(fb_filename): os.remove(fb_filename)

    # Test Chase Checking
    dummy_chase_content = (
        "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
        "DEBIT,05/01/2025,STARBUCKS STORE 123,-5.75,SALE,1000.00,\n"
        "CREDIT,05/03/2025,DIRECT DEPOSIT ACME CORP,1500.00,ACH_CREDIT,2494.25,\n"
    )
    chase_filename = os.path.join(test_files_dir, "test_chase_cli.csv")
    with open(chase_filename, 'w', encoding='utf-8') as f:
        f.write(dummy_chase_content)

    print(f"\n--- Testing Chase Checking CSV Parser (CLI context) ---")
    with open(chase_filename, 'rb') as chase_file_obj:
        chase_bytes_io = io.BytesIO(chase_file_obj.read())
    try:
        chase_transactions = parse_checking_csv(
            user_id=test_user_id_cli,
            file_obj=chase_bytes_io,
            filename="test_chase_cli.csv",
            project_id_override="Personal_Finance_CLI"  # Example project for checking
        )
        for tx in chase_transactions:
            print(f"Parsed Chase Tx: Date: {tx.date}, Desc: {tx.description}, Amount: {tx.amount}, "
                  f"Category: {tx.category}, Context: {tx.data_context}, Project: {tx.project_id}")
    except Exception as e_cli_chase:
        print(f"Error parsing Chase test CSV (CLI): {e_cli_chase}", exc_info=True)
    finally:
        if os.path.exists(chase_filename): os.remove(chase_filename)

    # Clean up test directory
    if os.path.exists(test_files_dir):
        try:
            os.rmdir(test_files_dir)  # Only removes if empty, which it should be now
        except OSError:
            log.warning(f"Could not remove temp test directory {test_files_dir}. It might not be empty.")

    log.info("Finished parser.py direct execution tests.")
