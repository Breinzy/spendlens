# parser.py
import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from typing import List, Dict, Optional, Any, Union, TextIO
import io

try:
    import database_supabase as database  # For FastAPI with Supabase
except ModuleNotFoundError:
    log_parser_standalone = logging.getLogger('parser_standalone_timelogs')
    log_parser_standalone.error("Failed to import 'database_supabase'. Using dummy for parser.py.")


    class DummyDB:
        def get_user_rules(self, user_id: str) -> Dict[str, str]: return {}

        def get_llm_rules(self, user_id: str) -> Dict[str, str]: return {}

        def save_user_rule(self, user_id: str, key: str, cat: str): pass

        def save_llm_rule(self, user_id: str, key: str, cat: str): pass


    database = DummyDB()  # type: ignore

log = logging.getLogger('parser')
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

VENDOR_RULES_FILE = 'vendors.json'


class Transaction:
    def __init__(self, id: Optional[int] = None, user_id: str = "", date: Optional[dt.date] = None,
                 # Added defaults for testing
                 description: Optional[str] = None, amount: Optional[Decimal] = None, category: Optional[str] = None,
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 created_at: Optional[dt.datetime] = None, updated_at: Optional[dt.datetime] = None):
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

    def to_dict(self) -> Dict[str, Any]:  # For serialization
        return {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if v is not None}


VENDOR_RULES = {}  # Loaded below


def load_vendor_rules(filepath: str) -> Dict[str, str]:
    # ... (implementation as before) ...
    rules: Dict[str, str] = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content: return {}
                rules = json.loads(content)
            log.info(f"Loaded {len(rules)} vendor rules from '{filepath}'.")
        except Exception as e:
            log.error(f"Error loading vendor rules from '{filepath}': {e}", exc_info=True)
            return {}
    else:
        log.warning(f"Vendor rules file not found: '{filepath}'.")
    return {k.lower(): v for k, v in rules.items()}


VENDOR_RULES = load_vendor_rules(VENDOR_RULES_FILE)


def add_user_rule(user_id: str, description_fragment: str, category: str):
    # ... (implementation as before) ...
    if not description_fragment or not category: return
    try:
        database.save_user_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save user rule for user {user_id}: {e}", exc_info=True)


def save_llm_rule(user_id: str, description_fragment: str, category: str):
    # ... (implementation as before) ...
    if not description_fragment or not category: return
    try:
        database.save_llm_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save LLM rule for user {user_id}: {e}", exc_info=True)


def categorize_transaction(user_id: str, description: str) -> str:
    # ... (implementation as before) ...
    if not description: return 'Uncategorized'
    desc_lower = description.lower()
    user_rules = database.get_user_rules(user_id)
    for key in sorted(user_rules.keys(), key=len, reverse=True):
        if key in desc_lower: return user_rules[key]
    for key in sorted(VENDOR_RULES.keys(), key=len, reverse=True):
        if key in desc_lower: return VENDOR_RULES[key]
    llm_rules = database.get_llm_rules(user_id)
    for key in sorted(llm_rules.keys(), key=len, reverse=True):
        if key in desc_lower: return llm_rules[key]
    return 'Uncategorized'


def parse_csv_with_schema(
        user_id: str, file_stream: TextIO, schema: Dict[str, Any],
        transaction_origin: str, source_filename: str, account_type: Optional[str] = None
) -> List[Transaction]:
    transactions: List[Transaction] = []
    log.info(f"User {user_id}: Schema parsing. Origin:'{transaction_origin}', File:'{source_filename}'")
    try:
        reader = csv.DictReader(file_stream)
        if not reader.fieldnames: raise ValueError(f"Empty/headerless CSV: {source_filename}")

        csv_headers_map = {name.lower().strip(): name for name in reader.fieldnames}

        def get_col_name(keys: List[str]) -> Optional[str]:
            for k_option in keys:
                norm_k = k_option.lower().strip()
                if norm_k in csv_headers_map: return csv_headers_map[norm_k]
            return None

        date_col = get_col_name(schema.get("date_fields", []))
        desc_col = get_col_name(schema.get("description_fields", []))
        amount_col = get_col_name(schema.get("amount_fields", []))
        type_col = get_col_name(schema.get("transaction_type_fields", []))
        category_col = get_col_name(schema.get("category_fields", []))
        client_name_col = get_col_name(schema.get("client_name_fields", []))
        invoice_id_col = get_col_name(schema.get("invoice_id_fields", []))
        project_id_col = get_col_name(schema.get("project_id_fields", []))
        payout_source_col_name = get_col_name(schema.get("payout_source_fields", []))
        # Time log specific (optional in schema)
        duration_col = get_col_name(schema.get("duration_fields", []))  # e.g., "Duration (decimal)"
        billable_rate_col = get_col_name(schema.get("billable_rate_fields", []))

        required_map = {"Date": date_col, "Description": desc_col}  # Amount might be optional for non-billable time
        missing = [k for k, v in required_map.items() if not v]
        if missing: raise ValueError(f"Missing essential columns in '{source_filename}': {', '.join(missing)}")

        date_format = schema.get("date_format", "%m/%d/%Y")  # Schema can specify date format

        for i, row in enumerate(reader):
            row_num = i + 2
            try:
                date_str = row.get(date_col) if date_col else None
                raw_desc_val = row.get(desc_col, '') if desc_col else ''
                amount_str = row.get(amount_col) if amount_col else None  # Amount can be missing

                if not date_str or not raw_desc_val:
                    log.warning(f"Row {row_num}: Skip due to missing date/description. File: {source_filename}")
                    continue
                description = ' '.join(raw_desc_val.strip().split())

                try:
                    transaction_date = dt.datetime.strptime(date_str, date_format).date()
                except ValueError:
                    try:
                        transaction_date = dateutil_parse(date_str).date()  # More flexible parsing
                    except (DateParserError, ValueError, TypeError):  # type: ignore
                        log.warning(
                            f"Row {row_num}: Skip due to unparseable date: '{date_str}'. File: {source_filename}")
                        continue

                amount_val = Decimal('0')  # Default to 0 if no amount
                if amount_str:
                    try:
                        amount_val = Decimal(amount_str.replace(',', '').replace('$', ''))  # Handle currency symbols
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid amount '{amount_str}', using 0. File: {source_filename}")
                # If amount is still 0, try to calculate from duration and rate for time logs
                elif transaction_origin in ['clockify_log', 'toggl_log'] and duration_col and billable_rate_col:
                    duration_str = row.get(duration_col)
                    rate_str = row.get(billable_rate_col)
                    if duration_str and rate_str:
                        try:
                            # Duration might be HH:MM:SS or decimal hours
                            duration_decimal_hours = Decimal('0')
                            if ':' in duration_str:  # HH:MM:SS or MM:SS
                                parts = duration_str.split(':')
                                if len(parts) == 3:  # HH:MM:SS
                                    duration_decimal_hours = Decimal(parts[0]) + Decimal(parts[1]) / 60 + Decimal(
                                        parts[2]) / 3600
                                elif len(parts) == 2:  # MM:SS
                                    duration_decimal_hours = Decimal(parts[0]) / 60 + Decimal(parts[1]) / 3600
                            else:  # Assume decimal hours
                                duration_decimal_hours = Decimal(duration_str)

                            rate_decimal = Decimal(rate_str.replace(',', '').replace('$', ''))
                            amount_val = duration_decimal_hours * rate_decimal
                            log.debug(
                                f"Row {row_num}: Calculated amount {amount_val} from duration '{duration_str}' and rate '{rate_str}'.")
                        except (InvalidOperation, ValueError, TypeError):
                            log.warning(
                                f"Row {row_num}: Could not calculate amount from duration/rate. Duration: '{duration_str}', Rate: '{rate_str}'. File: {source_filename}")

                # Skip if amount is effectively zero and it's not explicitly allowed by schema/origin type
                if amount_val == Decimal('0') and not schema.get("allow_zero_amount_transactions", False):
                    is_billable_col_name = get_col_name(schema.get("is_billable_fields", []))
                    is_billable_str = row.get(is_billable_col_name, "yes").lower() if is_billable_col_name else "yes"
                    if transaction_origin in ['clockify_log', 'toggl_log'] and is_billable_str in ['no', 'false', '0',
                                                                                                   'non-billable']:
                        log.debug(
                            f"Row {row_num}: Skipping non-billable zero-amount time entry. File: {source_filename}")
                        continue
                    # For other types, if amount is zero, might still be relevant (e.g. a $0 invoice line item)
                    # but for now, we'll focus on transactions with monetary value unless schema allows.

                tx_type_csv = row.get(type_col).strip() if type_col and row.get(type_col) else None
                tx_type = tx_type_csv if tx_type_csv else ('CREDIT' if amount_val > 0 else 'DEBIT')

                category_csv = row.get(category_col).strip() if category_col and row.get(category_col) else None
                category = category_csv if category_csv else categorize_transaction(user_id, description)
                if transaction_origin in ['clockify_log', 'toggl_log'] and category == 'Uncategorized':
                    category = "Time Tracking"  # Default category for time logs if not otherwise matched

                client_name = row.get(client_name_col).strip() if client_name_col and row.get(client_name_col) else None
                invoice_id = row.get(invoice_id_col).strip() if invoice_id_col and row.get(invoice_id_col) else None
                project_id = row.get(project_id_col).strip() if project_id_col and row.get(project_id_col) else None
                payout_source_val = row.get(payout_source_col_name).strip() if payout_source_col_name and row.get(
                    payout_source_col_name) else None

                transactions.append(Transaction(
                    user_id=user_id, date=transaction_date, description=description, amount=amount_val,
                    category=category, transaction_type=tx_type, source_account_type=account_type,
                    source_filename=source_filename, raw_description=raw_desc_val.strip(),
                    client_name=client_name, invoice_id=invoice_id, project_id=project_id,
                    payout_source=payout_source_val, transaction_origin=transaction_origin
                ))
            except Exception as row_err:
                log.error(f"Row {row_num}: Error processing. File: {source_filename}. Error: {row_err}", exc_info=True)
        log.info(f"User {user_id}: Parsed '{source_filename}'. Found {len(transactions)} txns.")
        return transactions
    except ValueError as ve:
        raise
    except Exception as e:
        log.error(f"User {user_id}: Fail to parse '{source_filename}': {e}", exc_info=True)
        raise RuntimeError(f"Failed to parse {source_filename} due to unexpected error.") from e


def _get_text_stream(user_id: str, file_like_object: Union[io.BytesIO, TextIO], filename: str,
                     parser_name: str) -> TextIO:
    if isinstance(file_like_object, io.BytesIO):
        return io.TextIOWrapper(file_like_object, encoding='utf-8-sig')
    if hasattr(file_like_object, 'readable') and callable(file_like_object.readable) and file_like_object.readable():
        return file_like_object
    log.error(f"User {user_id}: Invalid file object type '{type(file_like_object)}' for '{filename}' in {parser_name}.")
    raise TypeError(f"{parser_name} expects a BytesIO or TextIO object.")


CHASE_COMMON_SCHEMA = {
    "date_fields": ["Transaction Date", "Posting Date"], "description_fields": ["Description"],
    "amount_fields": ["Amount"], "transaction_type_fields": ["Type"], "date_format": "%m/%d/%Y"
}


def parse_checking_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_checking_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_checking', filename, 'checking')


def parse_credit_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_credit_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_credit', filename, 'credit')


STRIPE_PAYOUTS_SCHEMA = {
    "date_fields": ["created", "created_utc", "available_on", "available_on_utc", "date"],
    "description_fields": ["description", "summary", "charge id", "payment intent id"],  # Added more specific ID fields
    "amount_fields": ["net", "amount"],  # 'net' is often preferred for payouts
    "transaction_type_fields": ["type"],  # e.g., "payout", "charge", "refund", "fee", "stripe_fee"
    "invoice_id_fields": ["charge_id", "payment_intent_id", "source_id", "invoice"],
    # Stripe might have 'invoice' field
    "payout_source_fields": ["source_type", "card_brand"],  # e.g. "card_payment", "bank_transfer"
    "client_name_fields": ["customer_facing_descriptor", "customer_email", "customer_name", "metadata.client_name"],
    # Check metadata
    "date_format": "%Y-%m-%d %H:%M:%S",  # Common Stripe format, or use flexible dateutil_parse
    # Stripe amounts are often in cents. This needs to be handled.
    # We can add a "divisor" to the schema or handle in parse_csv_with_schema if a flag is set.
    # For now, assuming amounts are in currency units or handled by user pre-processing.
}


def parse_stripe_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_stripe_csv")
    return parse_csv_with_schema(user_id, s, STRIPE_PAYOUTS_SCHEMA, 'stripe_transaction', filename)


PAYPAL_TRANSACTIONS_SCHEMA = {
    "date_fields": ["Date"], "description_fields": ["Name", "Item Title", "Subject", "Note", "Type"],
    # Type can be descriptive
    "amount_fields": ["Net", "Gross"],  # 'Net' is usually the actual amount
    "transaction_type_fields": ["Type"],  # Often very descriptive in PayPal
    "invoice_id_fields": ["Invoice Number", "Transaction ID"],
    "client_name_fields": ["Name", "From Email Address"],
    "date_format": "%m/%d/%Y"
}


def parse_paypal_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_paypal_csv")
    return parse_csv_with_schema(user_id, s, PAYPAL_TRANSACTIONS_SCHEMA, 'paypal_transaction', filename)


GENERIC_INVOICE_SCHEMA = {
    "date_fields": ["Invoice Date", "Date Issued", "Payment Date", "Date"],
    "description_fields": ["Description", "Line Item Description", "Service Rendered", "Memo", "Item"],
    "amount_fields": ["Total Amount", "Amount Paid", "Net Amount", "Total", "Amount"],
    "client_name_fields": ["Client Name", "Customer", "Vendor Name", "Billed To"],
    "invoice_id_fields": ["Invoice #", "Invoice ID", "Reference Number", "Number"],
    "project_id_fields": ["Project Name", "Project Code", "Job"],
    "transaction_type_fields": ["Type", "Transaction Type"],
    "date_format": "%Y-%m-%d"  # Common export format, but flexible parsing helps
}


def parse_invoice_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_invoice_csv")
    return parse_csv_with_schema(user_id, s, GENERIC_INVOICE_SCHEMA, 'invoice_import', filename)


# --- New Time Log Parsers ---
CLOCKIFY_SCHEMA = {
    "date_fields": ["Start Date", "Date"],  # Clockify uses "Start Date"
    "description_fields": ["Description", "Task"],  # "Description" for time entry, "Task" if available
    "amount_fields": ["Billable Amount (USD)", "Billable Amount"],  # Prioritize this if present
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],  # Clockify uses "Project"
    "transaction_type_fields": [],  # Not directly applicable, might be derived
    "duration_fields": ["Duration (decimal)", "Duration (h)"],  # For calculating amount if rate is present
    "billable_rate_fields": ["Billable Rate (USD)", "Billable Rate"],
    "is_billable_fields": ["Billable"],  # To identify non-billable entries
    "date_format": "%Y-%m-%d",  # Clockify often uses YYYY-MM-DD for Start Date
    "allow_zero_amount_transactions": False  # Skip non-billable zero amount entries by default
}


def parse_clockify_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    """Parses a Clockify time tracking CSV export."""
    log.info(f"User {user_id}: Parsing Clockify CSV '{filename}'.")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_clockify_csv")
    # Specific logic for Clockify if needed, e.g. combining 'Description' and 'Task'
    # For now, parse_csv_with_schema should handle it based on schema priorities.
    return parse_csv_with_schema(user_id, text_stream, CLOCKIFY_SCHEMA,
                                 transaction_origin='clockify_log',
                                 source_filename=filename)


TOGGL_SCHEMA = {
    "date_fields": ["Start date"],  # Toggl uses "Start date"
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Amount (USD)", "Amount"],  # Toggl might have "Amount (CURRENCY_CODE)"
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "transaction_type_fields": [],  # Not directly applicable
    "duration_fields": ["Duration"],  # Toggl often has HH:MM:SS format for Duration
    "billable_rate_fields": ["Rate (USD)", "Rate"],  # Toggl might have "Rate (CURRENCY_CODE)"
    "is_billable_fields": ["Billable"],  # Yes/No
    "date_format": "%Y-%m-%d",  # Toggl often uses YYYY-MM-DD
    "allow_zero_amount_transactions": False
}


def parse_toggl_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    """Parses a Toggl Track time tracking CSV export."""
    log.info(f"User {user_id}: Parsing Toggl CSV '{filename}'.")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_toggl_csv")
    return parse_csv_with_schema(user_id, text_stream, TOGGL_SCHEMA,
                                 transaction_origin='toggl_log',
                                 source_filename=filename)


if __name__ == '__main__':
    log.info("parser.py executed directly for testing.")
    # ... (existing test setup) ...
    test_user_id = "parser_test_user_uuid"  # Example UUID

    # --- Test Clockify CSV ---
    dummy_clockify_fname = "test_clockify.csv"
    dummy_clockify_path = os.path.join("data_parser_test", dummy_clockify_fname)  # Assuming data_parser_test dir exists
    os.makedirs("data_parser_test", exist_ok=True)
    clockify_content = (
        "Project,Client,Description,Task,User,Email,Tags,Billable,Start Date,Start Time,End Date,End Time,Duration (h),Duration (decimal),Billable Rate (USD),Billable Amount (USD)\n"
        "Website Redesign,Client Alpha,Homepage mockups,Design,Test User,user@example.com,,Yes,2024-01-15,09:00:00,2024-01-15,11:30:00,2:30:00,2.5,50,125.00\n"
        "Internal Training,N/A,Documentation writing,Writing,Test User,user@example.com,,No,2024-01-16,10:00:00,2024-01-16,12:00:00,2:00:00,2.0,,0\n"  # Non-billable, zero amount
        "API Development,Client Beta,User auth endpoint,Coding,Test User,user@example.com,,Yes,2024-01-17,14:00:00,2024-01-17,17:00:00,3:00:00,3.0,60,180.00\n"
        "Consulting,Client Gamma,Strategy session,Meeting,Test User,user@example.com,,Yes,2024-01-18,10:00:00,2024-01-18,11:00:00,1.00,1,150,150\n"
    # Duration as decimal
    )
    with open(dummy_clockify_path, 'w', encoding='utf-8') as f:
        f.write(clockify_content)
    print(f"\n--- Testing Clockify CSV Parser ({dummy_clockify_fname}) ---")
    with open(dummy_clockify_path, 'rb') as fb:
        clockify_bytes = io.BytesIO(fb.read())
    try:
        clockify_txns = parse_clockify_csv(test_user_id, clockify_bytes, dummy_clockify_fname)
        for tx in clockify_txns: print(tx.to_dict())
    except Exception as e:
        print(f"Error parsing Clockify test CSV: {e}", exc_info=True)

    # --- Test Toggl CSV ---
    dummy_toggl_fname = "test_toggl.csv"
    dummy_toggl_path = os.path.join("data_parser_test", dummy_toggl_fname)
    toggl_content = (
        "User,Email,Client,Project,Task,Description,Billable,Start date,Start time,End date,End time,Duration,Tags,Amount (USD),Rate (USD)\n"  # Added Rate
        "Test User,user@example.com,Client Delta,Mobile App UI,UI Sketches,Initial concepts,Yes,2024-02-01,09:00:00,2024-02-01,11:00:00,02:00:00,design,100.00,50\n"
        "Test User,user@example.com,Client Epsilon,Marketing Campaign,Ad Copy,Drafting slogans,No,2024-02-02,14:00:00,2024-02-02,15:30:00,01:30:00,writing,,40\n"  # Non-billable, but has rate
        "Test User,user@example.com,Client Zeta,Server Maintenace,,Urgent fix,Yes,2024-02-03,16:00:00,2024-02-03,16:45:00,00:45:00,,75.00,100\n"
    # No Task
    )
    with open(dummy_toggl_path, 'w', encoding='utf-8') as f:
        f.write(toggl_content)
    print(f"\n--- Testing Toggl CSV Parser ({dummy_toggl_fname}) ---")
    with open(dummy_toggl_path, 'rb') as fb:
        toggl_bytes = io.BytesIO(fb.read())
    try:
        toggl_txns = parse_toggl_csv(test_user_id, toggl_bytes, dummy_toggl_fname)
        for tx in toggl_txns: print(tx.to_dict())
    except Exception as e:
        print(f"Error parsing Toggl test CSV: {e}", exc_info=True)

    log.info("Finished parser.py direct execution tests.")
