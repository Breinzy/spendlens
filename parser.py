# parser.py
import csv
import json
import logging
import os
from decimal import Decimal, InvalidOperation
import datetime as dt
from dateutil.parser import parse as dateutil_parse, ParserError as DateParserError  # For flexible date parsing
from typing import List, Dict, Optional, Any, Union, TextIO
import io

# --- Constants ---
DUMMY_CLI_USER_ID = "cli_report_user"

try:
    import database_supabase as database
except ModuleNotFoundError:
    log_parser_standalone = logging.getLogger('parser_standalone_timelogs')
    log_parser_standalone.warning("Failed to import 'database_supabase'. Using dummy for parser.py if run standalone.")


    class DummyDB:
        def get_user_rules(self, user_id: str) -> Dict[str, str]:
            log_parser_standalone.debug(f"DummyDB: get_user_rules called for {user_id}")
            return {}

        def get_llm_rules(self, user_id: str) -> Dict[str, str]:
            log_parser_standalone.debug(f"DummyDB: get_llm_rules called for {user_id}")
            return {}

        def save_user_rule(self, user_id: str, key: str, cat: str):
            log_parser_standalone.debug(f"DummyDB: save_user_rule called for {user_id}")
            pass

        def save_llm_rule(self, user_id: str, key: str, cat: str):
            log_parser_standalone.debug(f"DummyDB: save_llm_rule called for {user_id}")
            pass


    database = DummyDB()

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
                 description: Optional[str] = None, amount: Optional[Decimal] = None, category: Optional[str] = None,
                 transaction_type: Optional[str] = None, source_account_type: Optional[str] = None,
                 source_filename: Optional[str] = None, raw_description: Optional[str] = None,
                 client_name: Optional[str] = None, invoice_id: Optional[str] = None,
                 project_id: Optional[str] = None, payout_source: Optional[str] = None,
                 transaction_origin: Optional[str] = None,
                 rate: Optional[Decimal] = None,
                 quantity: Optional[Decimal] = None,
                 invoice_status: Optional[str] = None,  # Added invoice_status
                 date_paid: Optional[dt.date] = None,  # Added date_paid
                 created_at: Optional[dt.datetime] = None, updated_at: Optional[dt.datetime] = None):
        self.id = id
        self.user_id = user_id
        self.date = date  # Typically the invoice issue date or transaction date
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
        self.rate = rate
        self.quantity = quantity
        self.invoice_status = invoice_status
        self.date_paid = date_paid
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> Dict[str, Any]:
        return {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if v is not None}


VENDOR_RULES = {}


def load_vendor_rules(filepath: str) -> Dict[str, str]:
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
    if user_id == DUMMY_CLI_USER_ID:
        log.info(f"CLI mode: Skipping save_user_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category: return
    try:
        database.save_user_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save user rule for user {user_id}: {e}", exc_info=True)


def save_llm_rule(user_id: str, description_fragment: str, category: str):
    if user_id == DUMMY_CLI_USER_ID:
        log.info(f"CLI mode: Skipping save_llm_rule for '{description_fragment}' -> '{category}'")
        return
    if not description_fragment or not category: return
    try:
        database.save_llm_rule(user_id, description_fragment.lower().strip(), category)
    except Exception as e:
        log.error(f"Failed to save LLM rule for user {user_id}: {e}", exc_info=True)


def categorize_transaction(user_id: str, description: str) -> str:
    if not description: return 'Uncategorized'
    desc_lower = description.lower()
    if user_id == DUMMY_CLI_USER_ID:
        log.debug(f"Categorizing for CLI user: '{description}'")
        for key in sorted(VENDOR_RULES.keys(), key=len, reverse=True):
            if key in desc_lower:
                log.debug(f"CLI categorization: Matched VENDOR_RULE '{key}' -> '{VENDOR_RULES[key]}'")
                return VENDOR_RULES[key]
        log.debug(f"CLI categorization: No VENDOR_RULE match for '{description}'. Defaulting to Uncategorized.")
        return 'Uncategorized'

    log.debug(f"Categorizing for user {user_id}: '{description}'")
    user_rules = database.get_user_rules(user_id)
    for key in sorted(user_rules.keys(), key=len, reverse=True):
        if key in desc_lower:
            log.debug(f"User rule match: '{key}' -> '{user_rules[key]}'")
            return user_rules[key]
    for key in sorted(VENDOR_RULES.keys(), key=len, reverse=True):
        if key in desc_lower:
            log.debug(f"Vendor rule match: '{key}' -> '{VENDOR_RULES[key]}'")
            return VENDOR_RULES[key]
    llm_rules = database.get_llm_rules(user_id)
    for key in sorted(llm_rules.keys(), key=len, reverse=True):
        if key in desc_lower:
            log.debug(f"LLM rule match: '{key}' -> '{llm_rules[key]}'")
            return llm_rules[key]
    log.debug(f"No rule match for '{description}'. Defaulting to Uncategorized.")
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
        rate_col = get_col_name(schema.get("rate_fields", []))
        quantity_col = get_col_name(schema.get("quantity_fields", []))
        invoice_status_col = get_col_name(schema.get("invoice_status_fields", []))  # New
        date_paid_col = get_col_name(schema.get("date_paid_fields", []))  # New

        type_col = get_col_name(schema.get("transaction_type_fields", []))
        category_col = get_col_name(schema.get("category_fields", []))
        client_name_col = get_col_name(schema.get("client_name_fields", []))
        invoice_id_col = get_col_name(schema.get("invoice_id_fields", []))
        project_id_col = get_col_name(schema.get("project_id_fields", []))
        payout_source_col_name = get_col_name(schema.get("payout_source_fields", []))
        duration_col = get_col_name(schema.get("duration_fields", []))
        billable_rate_col = get_col_name(schema.get("billable_rate_fields", []))

        required_map = {"Date": date_col, "Description": desc_col, "Amount": amount_col}
        if transaction_origin in ['clockify_log', 'toggl_log'] and not amount_col:
            if not (duration_col and billable_rate_col):
                raise ValueError(
                    f"Missing essential columns for time log '{source_filename}': Needs Amount, or (Duration and Billable Rate)")
            else:
                del required_map["Amount"]

        missing = [k for k, v in required_map.items() if not v]
        if missing: raise ValueError(f"Missing essential columns in '{source_filename}': {', '.join(missing)}")

        date_format = schema.get("date_format")

        for i, row in enumerate(reader):
            row_num = i + 2
            try:
                date_str = row.get(date_col) if date_col else None
                raw_desc_val = row.get(desc_col, '') if desc_col else ''
                amount_str = row.get(amount_col) if amount_col else None
                rate_str = row.get(rate_col) if rate_col else None
                quantity_str = row.get(quantity_col) if quantity_col else None
                invoice_status_str = row.get(invoice_status_col).strip() if invoice_status_col and row.get(
                    invoice_status_col) else None  # New
                date_paid_str = row.get(date_paid_col) if date_paid_col else None  # New

                if not date_str or not raw_desc_val:
                    log.warning(f"Row {row_num}: Skip due to missing date/description. File: {source_filename}")
                    continue
                description = ' '.join(raw_desc_val.strip().split())

                try:
                    if date_format:
                        transaction_date = dt.datetime.strptime(date_str, date_format).date()
                    else:
                        transaction_date = dateutil_parse(date_str).date()
                except (DateParserError, ValueError, TypeError):
                    log.warning(f"Row {row_num}: Skip due to unparseable date: '{date_str}'. File: {source_filename}")
                    continue

                date_paid_val = None  # New
                if date_paid_str:
                    try:
                        if date_format:  # Assuming date_paid uses same format as issue date if specified
                            date_paid_val = dt.datetime.strptime(date_paid_str, date_format).date()
                        else:
                            date_paid_val = dateutil_parse(date_paid_str).date()
                    except (DateParserError, ValueError, TypeError):
                        log.warning(f"Row {row_num}: Unparseable Date Paid: '{date_paid_str}'. File: {source_filename}")
                        # Keep date_paid_val as None

                amount_val = Decimal('0')
                if amount_str:
                    try:
                        cleaned_amount_str = str(amount_str).replace('$', '').replace(',', '').strip()
                        if cleaned_amount_str.startswith('(') and cleaned_amount_str.endswith(')'):
                            cleaned_amount_str = '-' + cleaned_amount_str[1:-1]
                        amount_val = Decimal(cleaned_amount_str)
                    except InvalidOperation:
                        log.warning(
                            f"Row {row_num}: Invalid amount (line total) '{amount_str}', using 0. File: {source_filename}")

                rate_val = None
                if rate_str:
                    try:
                        cleaned_rate_str = str(rate_str).replace('$', '').replace(',', '').strip()
                        rate_val = Decimal(cleaned_rate_str)
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid rate '{rate_str}'. File: {source_filename}")

                quantity_val = None
                if quantity_str:
                    try:
                        quantity_val = Decimal(str(quantity_str).strip())
                    except InvalidOperation:
                        log.warning(f"Row {row_num}: Invalid quantity '{quantity_str}'. File: {source_filename}")

                if transaction_origin in ['clockify_log', 'toggl_log'] and (
                        not amount_str or amount_val == Decimal('0')):
                    if duration_col and billable_rate_col:
                        duration_str_tl = row.get(duration_col)
                        billable_rate_str_tl = row.get(billable_rate_col)
                        if duration_str_tl and billable_rate_str_tl:
                            try:
                                duration_decimal_hours = Decimal('0')
                                if ':' in duration_str_tl:
                                    parts = duration_str_tl.split(':')
                                    if len(parts) == 3:
                                        duration_decimal_hours = Decimal(parts[0]) + Decimal(parts[1]) / 60 + Decimal(
                                            parts[2]) / 3600
                                    elif len(parts) == 2:
                                        duration_decimal_hours = Decimal(parts[0]) / 60 + Decimal(parts[1]) / 3600
                                else:
                                    duration_decimal_hours = Decimal(duration_str_tl)

                                rate_decimal_tl = Decimal(str(billable_rate_str_tl).replace(',', '').replace('$', ''))
                                amount_val = duration_decimal_hours * rate_decimal_tl
                                rate_val = rate_decimal_tl
                                quantity_val = duration_decimal_hours
                            except (InvalidOperation, ValueError, TypeError):
                                log.warning(
                                    f"Row {row_num}: Could not calculate amount from time log duration/rate. Duration: '{duration_str_tl}', Rate: '{billable_rate_str_tl}'. File: {source_filename}")

                if amount_val == Decimal('0') and not schema.get("allow_zero_amount_transactions", False):
                    is_billable_col_name = get_col_name(schema.get("is_billable_fields", []))
                    is_billable_str = row.get(is_billable_col_name, "yes").lower() if is_billable_col_name else "yes"
                    if transaction_origin in ['clockify_log', 'toggl_log'] and is_billable_str in ['no', 'false', '0',
                                                                                                   'non-billable']:
                        log.debug(
                            f"Row {row_num}: Skipping non-billable zero-amount time entry. File: {source_filename}")
                        continue
                    elif transaction_origin not in ['clockify_log', 'toggl_log']:
                        log.debug(f"Row {row_num}: Skipping zero-amount transaction. File: {source_filename}")
                        continue

                tx_type_csv = row.get(type_col).strip() if type_col and row.get(type_col) else None
                tx_type = tx_type_csv if tx_type_csv else ('CREDIT' if amount_val > 0 else 'DEBIT')

                category_csv = row.get(category_col).strip() if category_col and row.get(category_col) else None
                category = category_csv if category_csv else categorize_transaction(user_id, description)
                if transaction_origin in ['clockify_log', 'toggl_log'] and category == 'Uncategorized':
                    category = "Time Tracking Revenue" if amount_val > 0 else "Time Tracking Expense/Cost"

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
                    payout_source=payout_source_val, transaction_origin=transaction_origin,
                    rate=rate_val, quantity=quantity_val,
                    invoice_status=invoice_status_str, date_paid=date_paid_val  # New fields
                ))
            except Exception as row_err:
                log.error(f"Row {row_num}: Error processing. File: {source_filename}. Error: {row_err}", exc_info=False)
        log.info(f"User {user_id}: Parsed '{source_filename}'. Found {len(transactions)} txns.")
        return transactions
    except ValueError as ve:
        log.error(f"User {user_id}: Value error parsing '{source_filename}': {ve}", exc_info=False)
        raise
    except Exception as e:
        log.error(f"User {user_id}: Unexpected error parsing '{source_filename}': {e}", exc_info=True)
        raise RuntimeError(f"Failed to parse {source_filename} due to an unexpected error.") from e


def _get_text_stream(user_id: str, file_like_object: Union[io.BytesIO, TextIO], filename: str,
                     parser_name: str) -> TextIO:
    if isinstance(file_like_object, io.BytesIO):
        try:
            return io.TextIOWrapper(file_like_object, encoding='utf-8-sig')
        except UnicodeDecodeError:
            log.warning(f"User {user_id}: UTF-8 decoding failed for '{filename}' in {parser_name}. Trying latin-1.")
            file_like_object.seek(0)
            return io.TextIOWrapper(file_like_object, encoding='latin-1')
    if hasattr(file_like_object, 'readable') and callable(file_like_object.readable) and file_like_object.readable():
        return file_like_object
    log.error(f"User {user_id}: Invalid file object type '{type(file_like_object)}' for '{filename}' in {parser_name}.")
    raise TypeError(f"{parser_name} expects a BytesIO or TextIO object.")


CHASE_COMMON_SCHEMA = {
    "date_fields": ["Transaction Date", "Posting Date"], "description_fields": ["Description"],
    "amount_fields": ["Amount"], "transaction_type_fields": ["Type"], "date_format": "%m/%d/%Y"
}  # ... (other schemas remain the same)


def parse_checking_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_checking_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_checking', filename, 'checking')


def parse_credit_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_credit_csv")
    return parse_csv_with_schema(user_id, s, CHASE_COMMON_SCHEMA, 'chase_credit', filename, 'credit')


STRIPE_PAYOUTS_SCHEMA = {
    "date_fields": ["created", "created_utc", "available_on", "available_on_utc", "date"],
    "description_fields": ["description", "summary", "charge id", "payment intent id"],
    "amount_fields": ["net", "amount"],
    "transaction_type_fields": ["type"],
    "invoice_id_fields": ["charge_id", "payment_intent_id", "source_id", "invoice"],
    "payout_source_fields": ["source_type", "card_brand"],
    "client_name_fields": ["customer_facing_descriptor", "customer_email", "customer_name", "metadata.client_name"],
    "date_format": None,
}


def parse_stripe_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_stripe_csv")
    return parse_csv_with_schema(user_id, s, STRIPE_PAYOUTS_SCHEMA, 'stripe_transaction', filename)


PAYPAL_TRANSACTIONS_SCHEMA = {
    "date_fields": ["Date"], "description_fields": ["Name", "Item Title", "Subject", "Note", "Type"],
    "amount_fields": ["Net", "Gross"],
    "transaction_type_fields": ["Type"],
    "invoice_id_fields": ["Invoice Number", "Transaction ID"],
    "client_name_fields": ["Name", "From Email Address"],
    "date_format": "%m/%d/%Y"
}


def parse_paypal_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_paypal_csv")
    return parse_csv_with_schema(user_id, s, PAYPAL_TRANSACTIONS_SCHEMA, 'paypal_transaction', filename)


GENERIC_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Invoice Date", "Payment Date", "Date"],
    "description_fields": ["Item Description", "Item Name", "Description", "Line Item Description", "Service Rendered",
                           "Memo"],
    "amount_fields": ["Line Total", "Total Amount", "Amount Paid", "Net Amount", "Total", "Amount"],
    "rate_fields": ["Rate", "Unit Price", "Price"],
    "quantity_fields": ["Quantity", "Qty", "Hours"],
    "client_name_fields": ["Client Name", "Customer", "Vendor Name", "Billed To"],
    "invoice_id_fields": ["Invoice #", "Invoice ID", "Reference Number", "Number"],
    "project_id_fields": ["Project Name", "Project Code", "Job"],
    "transaction_type_fields": ["Type", "Transaction Type"],
    "invoice_status_fields": ["Invoice Status", "Status"],  # Added for generic invoices
    "date_paid_fields": ["Date Paid", "Payment Date"],  # Added for generic invoices
    "date_format": "%Y-%m-%d"
}


def parse_invoice_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    s = _get_text_stream(user_id, file_obj, filename, "parse_invoice_csv")
    return parse_csv_with_schema(user_id, s, GENERIC_INVOICE_SCHEMA, 'invoice_import', filename)


FRESHBOOKS_INVOICE_SCHEMA = {
    "date_fields": ["Date Issued", "Date"],  # Primary date for the line item
    "description_fields": ["Item Description", "Item Name", "Description"],
    "amount_fields": ["Line Total", "Amount"],
    "rate_fields": ["Rate"],
    "quantity_fields": ["Quantity"],
    "client_name_fields": ["Client Name"],
    "invoice_id_fields": ["Invoice #", "Invoice Number"],
    "project_id_fields": ["Project Name", "Project"],
    "transaction_type_fields": ["Type"],  # Less relevant if we use Invoice Status
    "invoice_status_fields": ["Invoice Status"],  # Key field for FreshBooks
    "date_paid_fields": ["Date Paid"],  # Key field for FreshBooks
    "date_format": "%Y-%m-%d",  # Matches your sample
    "allow_zero_amount_transactions": True
}


def parse_freshbooks_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    log.info(f"User {user_id}: Parsing FreshBooks CSV '{filename}'.")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_freshbooks_csv")
    return parse_csv_with_schema(user_id, text_stream, FRESHBOOKS_INVOICE_SCHEMA,
                                 transaction_origin='freshbooks_invoice',
                                 source_filename=filename)


CLOCKIFY_SCHEMA = {
    "date_fields": ["Start Date", "Date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Billable Amount (USD)", "Billable Amount"],
    "billable_rate_fields": ["Billable Rate (USD)", "Billable Rate"],
    "duration_fields": ["Duration (decimal)", "Duration (h)"],
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "transaction_type_fields": [],
    "is_billable_fields": ["Billable"],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": False
}


def parse_clockify_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    log.info(f"User {user_id}: Parsing Clockify CSV '{filename}'.")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_clockify_csv")
    return parse_csv_with_schema(user_id, text_stream, CLOCKIFY_SCHEMA,
                                 transaction_origin='clockify_log',
                                 source_filename=filename)


TOGGL_SCHEMA = {
    "date_fields": ["Start date"],
    "description_fields": ["Description", "Task"],
    "amount_fields": ["Amount (USD)", "Amount"],
    "billable_rate_fields": ["Rate (USD)", "Rate"],
    "duration_fields": ["Duration"],
    "client_name_fields": ["Client"],
    "project_id_fields": ["Project"],
    "transaction_type_fields": [],
    "is_billable_fields": ["Billable"],
    "date_format": "%Y-%m-%d",
    "allow_zero_amount_transactions": False
}


def parse_toggl_csv(user_id: str, file_obj: Union[io.BytesIO, TextIO], filename: str) -> List[Transaction]:
    log.info(f"User {user_id}: Parsing Toggl CSV '{filename}'.")
    text_stream = _get_text_stream(user_id, file_obj, filename, "parse_toggl_csv")
    return parse_csv_with_schema(user_id, text_stream, TOGGL_SCHEMA,
                                 transaction_origin='toggl_log',
                                 source_filename=filename)


if __name__ == '__main__':
    log.info("parser.py executed directly for testing.")
    test_user_id = DUMMY_CLI_USER_ID
    os.makedirs("data_parser_test", exist_ok=True)

    dummy_freshbooks_fname = "test_freshbooks_invoice_status.csv"
    dummy_freshbooks_path = os.path.join("data_parser_test", dummy_freshbooks_fname)
    freshbooks_content_status = (
        "Client Name,Invoice #,Date Issued,Invoice Status,Date Paid,Item Name,Item Description,Rate,Quantity,Line Total,Currency\n"
        "Client Alpha,INV-001,2025-05-01,paid,2025-05-10,Web Design,Homepage Mockup,75.00,10.0,750.00,USD\n"
        "Client Beta,INV-002,2025-05-03,sent,,Consulting,Strategy Session,150.00,2.0,300.00,USD\n"
        "Client Alpha,INV-003,2025-05-15,overdue,,Logo Design,Brand Logo,60.00,1.0,60.00,USD\n"
        "Client Gamma,INV-004,2025-04-20,draft,,Support,Monthly Retainer,200.00,1.0,200.00,USD\n"
        "Client Delta,INV-005,2025-03-01,paid,2025-03-10,Hourly Work,Task Completion,80.00,5.0,400.00,USD\n"
        "Client Epsilon,INV-006,2025-05-20,viewed,,Project Setup,Initial Config,100.00,1.0,100.00,USD\n"
    )
    with open(dummy_freshbooks_path, 'w', encoding='utf-8') as f:
        f.write(freshbooks_content_status)
    print(f"\n--- Testing FreshBooks CSV Parser with Invoice Status ({dummy_freshbooks_fname}) ---")
    with open(dummy_freshbooks_path, 'rb') as fb:
        freshbooks_bytes = io.BytesIO(fb.read())
    try:
        freshbooks_txns = parse_freshbooks_csv(test_user_id, freshbooks_bytes, dummy_freshbooks_fname)
        for tx in freshbooks_txns:
            print(
                f"Parsed FreshBooks Tx: Client: {tx.client_name}, Amount: {tx.amount}, Invoice Status: {tx.invoice_status}, Date Paid: {tx.date_paid}, Desc: {tx.description}")
    except Exception as e:
        print(f"Error parsing FreshBooks test CSV: {e}", exc_info=True)

    log.info("Finished parser.py direct execution tests.")
